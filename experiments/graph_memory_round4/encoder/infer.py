"""Sealed CPU inference. No parquet, gold labels, downstream outcomes or scorer imports."""
import os
os.environ.update(HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TOKENIZERS_PARALLELISM="false", CUDA_VISIBLE_DEVICES="")
import hashlib
import platform
import statistics
import time
import numpy as np
import torch
import transformers
from common_run import D, hashfile, load, now, readgz, save, writegz
from repo_unixcoder import UniXcoder

THREADS = 6
torch.set_num_threads(THREADS)
torch.set_num_interop_threads(1)
torch.manual_seed(20261118)
t = time.monotonic()
receipt = load(D / "inputs_receipt.json")
assert hashfile(D / "blind.jsonl.gz") == receipt["blind_sha"]
packets = list(readgz(D / "blind.jsonl.gz"))
model = UniXcoder(str(D / "weights")).cpu().eval()
loaded = time.monotonic()
texts = sorted({s for p in packets for s in [*p["candidates"], *p["queries"].values()]}, key=lambda s:hashlib.sha256(s.encode()).hexdigest())
tokens = {}
for s in texts:
    tokens[s] = tuple(model.tokenize([s], mode="<encoder-only>", max_length=512)[0]) if s else ()
seqs = sorted(set(tokens.values())-{()}, key=lambda v:(len(v),v))
clock = time.monotonic()
vectors = {():torch.zeros(model.config.hidden_size)}
seqtoken = padtoken = batches = 0
with torch.inference_mode():
    i = 0
    while i < len(seqs):
        size = min(24, max(2, 1600 // len(seqs[i])))
        seq = seqs[i:i+size]
        lengths = [len(k) for k in seq]
        padded = torch.full((len(seq),max(lengths)), model.config.pad_token_id, dtype=torch.long)
        for j,x in enumerate(seq):
            padded[j,:len(x)] = torch.tensor(x)
        _, embeddings = model(padded)
        for j,x in enumerate(seq):
            vectors[x] = embeddings[j].clone()
        i += len(seq)
        seqtoken += sum(lengths)
        padtoken += padded.numel()
        batches += 1
        if batches % 12 == 1 or i==len(seqs):
            print(f"{now()} seq={i}/{len(seqs)} len={max(lengths)} counttokens={seqtoken} took={time.monotonic()-clock:.1f}s",flush=True)
    end_embed = time.monotonic()
    single = {}
    def standalone(seq):
        if seq not in single:
            single[seq] = model(torch.tensor([seq]))[1][0].clone() if seq else vectors[()]
        return single[seq]
    sanity = []
    for s in texts[:12]:
        v, w = standalone(tokens[s]), vectors[tokens[s]]
        sanity.append({"text_sha":hashlib.sha256(s.encode()).hexdigest(),"max_abs":(v-w).abs().max().item(),"cos":torch.cosine_similarity(v,w,dim=0).item()})
    assert max(r["max_abs"] for r in sanity) < 1e-4, sanity
    out = []
    close_queries = changed_orders = 0
    for p in packets:
        candidates = [tokens[c] for c in p["candidates"]]
        for tag, s in p["queries"].items():
            q = tokens[s]
            def similarity(qv, keys):
                return [torch.cosine_similarity(qv,v,dim=0).item() for v in keys]
            scores = similarity(vectors[q], [vectors[c] for c in candidates])
            order = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
            close = set()
            for a,b in zip(order,order[1:]):
                if candidates[a] != candidates[b] and abs(scores[a]-scores[b]) < 2e-5:
                    close.update((a,b))
            if close:
                close_queries += 1
                # Exact single-item implementation for this entire query whenever numerical noise could change a rank.
                ref = similarity(standalone(q), [standalone(c) for c in candidates])
                seqorder = sorted(range(len(ref)),key=ref.__getitem__,reverse=True)
                changed_orders += int(seqorder!=order)
                scores, order = ref, seqorder
            out.append({"panel":p["panel"],"idx":p["idx"],"project":p["project"],"query":tag,"rank":order,"cosine":scores})
writegz(D/"predictions.jsonl.gz",out)
end=time.monotonic()
info=dict(utc=now(), method_sha=hashfile(D/"method_lock.json"), pred_sha=hashfile(D/"predictions.jsonl.gz"),infer_sha=hashfile(D/"infer.py"),input_sha=receipt["blind_sha"],dtype="float32",processor=platform.processor(),device=str(next(model.parameters()).device),torch=torch.__version__,transformers=transformers.__version__,threads=THREADS,attn_impl=model.model.config._attn_implementation,unique_sequences=len(seqs),lengths=[int(x) for x in np.quantile([len(k) for k in seqs],[0,.25,.5,.75,1])],tokens=seqtoken,paddedtokens=padtoken,batches=batches,all_unique_texts=len(texts),queries=len(out),near_tie_queries=close_queries,near_tie_changed=changed_orders,single_vectors=len(single),independent_checks=sanity,load_seconds=loaded-t,tokenize_seconds=clock-loaded,batch_embed_seconds=end_embed-clock,ranking_audit_seconds=end-end_embed,total_seconds=end-t)
save("prediction_lock.json",info)
print(info,flush=True)

"""Independent additional paper-method control: Stella V5 1.5B session retrieval."""
import argparse
import csv
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from safetensors.torch import load_file
from transformers import AutoModel, AutoTokenizer

from rank import HERE, order, vector_key
from evaluate import INDEX
from upstream.eval_utils import evaluate_retrieval


def compute_embeddings(path, texts, batch_size):
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=True)
    model = AutoModel.from_pretrained(path, local_files_only=True, trust_remote_code=True,
                                     torch_dtype=torch.bfloat16).eval().cuda()
    linear = torch.nn.Linear(model.config.hidden_size, 1024)
    state = load_file(str(path / "2_Dense_1024" / "model.safetensors"))
    linear.load_state_dict({k.removeprefix("linear."):v for k,v in state.items()})
    linear = linear.eval().cuda()
    vectors = np.empty((len(texts), 1024), dtype=np.float32)
    start = time.perf_counter()
    n_tokens = 0
    with torch.inference_mode():
        for i in range(0, len(texts), batch_size):
            inputs = tokenizer(texts[i:i + batch_size], truncation=True, padding="longest",
                               max_length=512, return_tensors="pt").to("cuda")
            mask = inputs.attention_mask.bool()
            last = model(**inputs, use_cache=False).last_hidden_state.float()
            pooled = last.masked_fill(~mask[...,None],0.).sum(1) / mask.sum(1)[:,None]
            vectors[i:i + batch_size] = F.normalize(linear(pooled),p=2,dim=1).cpu().numpy()
            n_tokens += int(mask.sum().item())
            if i % (batch_size * 100) == 0:
                print(i,len(texts),round(time.perf_counter()-start,1),flush=True)
    return vectors, dict(unique_strings=len(texts), tokens=n_tokens, seconds=time.perf_counter()-start,
                         cuda_peak_bytes=torch.cuda.max_memory_allocated(), precision="BF16 encoder / FP32 pool and head",
                         batch=batch_size, gpu=torch.cuda.get_device_name())


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("cache", type=Path)
    cli.add_argument("--batch", type=int, default=32)
    args = cli.parse_args()
    data_path = args.cache / "longmemeval_s_cleaned.json"
    raw = json.loads(data_path.read_text("utf-8"))
    rows = [(r["question"],[" ".join(t["content"] for t in s if t["role"]=="user")
                             for s in r["haystack_sessions"]]) for r in raw]
    del raw
    strings = {s for _, corpus in rows for s in corpus}
    strings.update(q for q,_ in rows)
    texts = sorted(strings,key=lambda t:(len(t),vector_key(t)))
    vectors, resources = compute_embeddings(args.cache / "stella", texts, args.batch)
    lookup = {text:i for i,text in enumerate(texts)}
    ranks = [order(vectors[[lookup[t] for t in corpus]] @ vectors[lookup[q]]).tolist() for q,corpus in rows]
    (HERE/"stella_ranks.jsonl").write_text("".join(json.dumps(dict(row=i,query_sha256=vector_key(q),ranks=rank))+"\n"
                         for i,((q,_),rank) in enumerate(zip(rows,ranks))),encoding="utf-8")
    raw = json.loads(data_path.read_text("utf-8"))
    scored = []
    for item, ranking in zip(raw,ranks):
        if "_abs" in item["question_id"]:
            continue
        ids = item["haystack_session_ids"]
        callback = [(s,c,d) for s,c,d in zip(item["haystack_sessions"],ids,item["haystack_dates"])]
        processed = [INDEX(s,"session",c,d)[1][0] for s,c,d in callback]
        user_gold = [c for c in processed if "answer" in c]
        schemes = [("declared_470",ids,item["answer_session_ids"])]
        if any(t.get("has_answer",False) for s,_,_ in callback for t in s if t["role"]=="user"):
            schemes.append(("official_419",processed,user_gold))
        for scheme, corpus, gold in schemes:
            any5, all5, ndcg5 = evaluate_retrieval(ranking,gold,corpus,5)
            scored.append(dict(question_id=item["question_id"],scheme=scheme,any5=int(any5),
                               all5=int(all5),official_ndcg5=float(ndcg5)))
    with (HERE/"stella_per_question.csv").open("w",encoding="utf-8",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=scored[0])
        writer.writeheader()
        writer.writerows(scored)
    summary = dict(resources=resources)
    for scheme in ("declared_470","official_419"):
        group = [s for s in scored if s["scheme"]==scheme]
        summary[scheme] = dict(n=len(group),any5=sum(x["any5"] for x in group),
                               all5=sum(x["all5"] for x in group),
                               official_ndcg5=np.mean([x["official_ndcg5"] for x in group]))
    (HERE/"stella_results.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(summary,flush=True)


if __name__ == "__main__":
    main()

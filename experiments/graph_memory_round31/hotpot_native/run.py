"""CPU replication of both author scoring heads and policy-dependent search pools."""
import argparse
import gc
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIVATE = Path("D:/CodexResearch/x20-r31-hotpot-native")
BLIND = Path("D:/CodexResearch/x20-r31-hotpot/blind.json.gz")
UP = PRIVATE / "upstream"
WEIGHTS = PRIVATE / "weights"
MODEL = WEIGHTS / "hotpot_beam2_retr.pt"
DIGEST = "61d2cc8875a1ed29186530abf017308c1f229509b33f4a26332e768a5cc09858"
sys.path[:0] = [str(PRIVATE / "deps312"), str(UP)]

def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def read(path):
    return json.loads(path.read_text(encoding="utf8"))

def put(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":")) + "\n", encoding="utf8")
    temp.replace(path)

def inputs():
    with gzip.open(BLIND,"rt",encoding="utf8") as f:
        return json.load(f)

def freeze():
    corpus = inputs()
    eligible = [q for q,r in corpus.items() if len(r["titles"])==len(r["sentences"])==10]
    order = sorted(eligible,key=lambda q:hashlib.sha256(("r31-native-beam-v1/"+q).encode()).digest())
    put(HERE/"plan.json",{"code":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md"),"families":sha(HERE.parent/"support_pairs"/"families.py"),"blind":sha(BLIND),"no_gold":True,"eligible":len(eligible),"panel":order[:8],"pilot":4,"wall_minutes":90,"model_sha":DIGEST,"author_code":{p.name:sha(p) for p in UP.iterdir() if p.is_file()},"tokenizer":{k:sha(WEIGHTS/k) for k in ("config.json","tokenizer_config.json","spm.model")}})
    print("Frozen", order[:8], flush=True)

def load_model():
    import torch
    from torch import nn
    from transformers import AutoConfig, AutoTokenizer, DebertaV2Model
    from retriever_model import Retriever
    tok = AutoTokenizer.from_pretrained(str(WEIGHTS),local_files_only=True)
    cfg = AutoConfig.from_pretrained(str(WEIGHTS),local_files_only=True)
    cfg.sep_token_id = tok.sep_token_id
    cfg.cls_token_id = tok.cls_token_id
    class OfflineEncoder:
        @staticmethod
        def from_pretrained(path,config):
            return DebertaV2Model(config)
    with torch.device("meta"):
        model = Retriever(cfg, str(WEIGHTS), OfflineEncoder, mean_passage_len=250,beam_size=10)
    state = torch.load(MODEL, weights_only=True, mmap=True, map_location="cpu")
    state = {key.removeprefix("module."):value for key,value in state.items()}
    # Historical HF versions persist position_ids. Newer versions regenerate the identical range.
    expected = model.state_dict()
    ignored = {}
    for key in set(state).difference(expected):
        if key == "encoder.embeddings.position_ids" and torch.equal(state[key].reshape(-1),torch.arange(state[key].numel())):
            ignored[key] = "deterministic arange positional IDs"
        else:
            raise RuntimeError("Unmapped checkpoint field "+key)
    model.load_state_dict({k:v for k,v in state.items() if k not in ignored},strict=True,assign=True)
    for mod in model.modules():
        for key,t in mod._buffers.items():
            if t is not None and t.device.type=="meta":
                if key!="position_ids":
                    raise RuntimeError("Uninitialized nonpersistent buffer "+key)
                mod._buffers[key] = torch.arange(t.numel(),dtype=t.dtype).reshape(t.shape)
    assert all(v.dtype==torch.float32 for v in model.parameters())
    model.eval()
    stock = model.encoder.forward
    calls=[]
    def microbatch(input_ids,attention_mask):
        # Only CLS vectors are accessed in the author's forward. Masked right padding is removed.
        cols = (attention_mask.sum(1)+1).tolist()
        out=[]
        for i in range(len(cols)):
            s=time.monotonic()
            z=stock(input_ids=input_ids[i:i+1,:cols[i]],attention_mask=attention_mask[i:i+1,:cols[i]])[0][:,:1,:].clone()
            out.append(z)
            calls.append([cols[i],round(time.monotonic()-s,5)])
        return (torch.cat(out,dim=0),)
    model.encoder.forward = microbatch
    print("loaded",len(state),"keys",sum(x.numel() for x in model.parameters()),"parameters",ignored,flush=True)
    return model,tok,calls

def predict(model,tok,record,docs,beam):
    import torch
    q=tok.encode(record["q"].removesuffix("?"),add_special_tokens=False,return_tensors="pt",truncation=True,max_length=512).squeeze(0)
    cs=[tok.encode(record["titles"][i]+"".join(record["sentences"][i]),add_special_tokens=False,return_tensors="pt",truncation=True,max_length=512-len(q)).squeeze(0) for i in docs]
    logits=[]
    handles=[h.register_forward_hook(lambda module,args,result:logits.append(result[:,1].detach().clone())) for h in (model.hop_classifier_layer,model.hop_n_classifier_layer)]
    model.beam_size=beam
    try:
        with torch.inference_mode(): output=model([q],[cs],[],hop=2)
    finally:
        for h in handles: h.remove()
    order=logits[0].topk(beam).indices.tolist()
    visited=set(); pairs=[]
    for first in order:
        visited.add(first)
        pairs.extend((docs[first],docs[j]) for j in range(len(docs)) if j not in visited)
    assert len(pairs)==len(logits[1])
    pred=[[docs[x] for x in p] for p in output["current_preds"]]
    ranked=[[*p,float(v)] for p,v in zip(pairs,logits[1].tolist())]
    ranked.sort(key=lambda row:(-row[2],row[0],row[1]))
    assert set(ranked[0][:2])==set(pred[0])
    return {"doc_scores":dict(zip(docs,logits[0].tolist())),"doc_order":[docs[x] for x in order],"pairs":ranked,"native_top":pred,"first_tokens":len(q),"context_tokens":[len(x) for x in cs],"score_ties":len(ranked)-len({p[2] for p in ranked})}

def run():
    import psutil
    import torch
    import transformers
    proc=psutil.Process()
    if hasattr(psutil,"BELOW_NORMAL_PRIORITY_CLASS"): proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    plan=read(HERE/"plan.json")
    assert sha(Path(__file__))==plan["code"] and sha(HERE/"PROTOCOL_RU.md")==plan["protocol"] and sha(BLIND)==plan["blind"]
    if not MODEL.is_file():
        part=MODEL.with_suffix(".pt.part")
        assert sha(part)==DIGEST
        part.replace(MODEL)
    else: assert sha(MODEL)==DIGEST
    t0=time.monotonic()
    model,tok,calls=load_model()
    corpus=inputs()
    outdir=HERE/"forecasts";outdir.mkdir(exist_ok=True)
    began=0
    for index,q in enumerate(plan["panel"]):
        dst=outdir/(q+".json")
        if dst.exists():
            previous=read(dst); assert previous["plan"]==sha(HERE/"plan.json")
            began+=previous["wall_s"];continue
        if time.monotonic()-t0+began>5400 or psutil.virtual_memory().available<3*1024**3: break
        t=time.monotonic();calls.clear()
        print("starting",index+1,q,flush=True)
        full=predict(model,tok,corpus[q],list(range(10)),10)
        extra=None
        if index==0:
            banned=full["doc_order"][0]
            remaining=[i for i in range(10) if i!=banned]
            rerun=predict(model,tok,corpus[q],remaining,2)
            available=[i for i in full["doc_order"] if i!=banned][:2]
            projected=[p for p in full["pairs"] if banned not in p[:2] and any(i in available for i in p[:2])]
            direct={tuple(p[:2]):p[2] for p in rerun["pairs"]}
            assert set(direct)=={tuple(p[:2]) for p in projected}
            max_err=max(abs(p[2]-direct[tuple(p[:2])]) for p in projected)
            assert set(projected[0][:2])==set(rerun["native_top"][0])
            extra={"banned":banned,"direct":rerun,"max_pair_abs":max_err,"actual_top_agrees":True}
        info={"question":q,"plan":sha(HERE/"plan.json"),"stage":"pilot" if index<4 else "replication","full":full,"physical_check":extra,"encoder_calls":calls,"wall_s":time.monotonic()-t,"rss_peak_bytes":getattr(proc.memory_info(),"peak_wset",proc.memory_info().rss),"available_ram":psutil.virtual_memory().available,"torch":torch.__version__,"transformers":transformers.__version__,"device":"cpu","threads":2}
        put(dst,info)
        print("completed",index+1,round(info["wall_s"],2),"seconds",info["rss_peak_bytes"],"B",flush=True)
        gc.collect()
    done={p.stem:sha(p) for p in sorted(outdir.glob("*.json"))}
    put(HERE/"ranking-seal.json",{"plan":sha(HERE/"plan.json"),"forecasts":done,"expected":len(plan["panel"]),"complete":len(done)==len(plan["panel"]),"model":DIGEST})

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=["freeze","run"]);args=parser.parse_args()
    if args.mode=="freeze":freeze()
    else:run()

"""Stream bounded archives then score native exact spans on saved decisions."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import gzip
import json
import os
import sys
for s in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[s]="1"
import numpy as np
from statistics import mean
D=Path(__file__).resolve().parent;OLD=D.parents[1]/"graph_memory_round19"
sys.path.insert(0,str(OLD/"write_learned"))
from features import stream,rows,tool_lookup,design,load,save,sha
def inputs(stage,i):
    if stage=="test":
        return (OLD/f"online_write/forecast-{i}.jsonl.gz",OLD/f"write_learned/forecast-{i}.jsonl.gz",stream.CACHE)
    return (OLD/f"write_transfer/predictions-{i}.jsonl.gz",OLD/f"write_learned/transfer-dev-{i}.jsonl.gz",Path("D:/CodexResearch/x20-isetrace-runtime/write-dev-private/projection"))
def predict_shard(job):
    stage,i=job;source,previous,cache=inputs(stage,i);dest=D/f"{stage}-decisions-{i}.jsonl.gz"
    model=load(D/"model.json");base=load(OLD/"write_learned/model.json");assert model["base"]==sha(OLD/"write_learned/model.json")
    f=base["arms"]["full"]
    with gzip.open(source,"rb") as src,gzip.open(previous,"rb") as ref,gzip.open(dest,"wt",encoding="utf8",compresslevel=3) as fo:
        for line,oldline in zip(src,ref,strict=True):
            r=json.loads(line);t=r["t"];prev=json.loads(oldline);assert prev["t"]==t
            raw=load(cache/f"{i}-{t}.json.gz");assert raw["t"]==t
            ad,bl=r["addresses"],r["blocks"];fields=raw["fields"]
            z,tools=rows(ad,bl,fields,tool_lookup(raw["pool"]));x=(design(z,tools,base["tools"],True)-f["means"])/f["scale"]
            ties=[stream.stable(eid) for eid,_ in ad];cost=[b[3] for b in bl]
            # Match R19 float probability tie semantics even at saturation.
            kept={}
            for arm,w in model["coef"].items():
                val=1/(1+np.exp(-np.clip(x@w+f["intercept"],-700,700)))
                kept[arm]=stream.select(cost,[((-float(v),ties[b[0]]),) for b,v in zip(bl,val,strict=True)],0,8192)
            q=[(i,stream.content_tokens(txt)) for i,txt in raw["q"]]
            words=[stream.content_tokens(fields[ad[e][0]][a:b]) for e,a,b,_,_ in bl]
            arms={k:[keep,stream.read(keep,cost,words,q)] for k,keep in kept.items()}
            assert arms["frozen"]==prev["a"]["tokens/full"][:2]
            fo.write(json.dumps({"t":t,"a":arms},separators=(",",":"))+"\n")
    return sha(dest)
def predict(stage):
    with ProcessPoolExecutor(3) as pool:hashes=list(pool.map(predict_shard,[(stage,i) for i in range(8)]))
    save(D/(stage+"-seal.json"),{"model":sha(D/"model.json"),"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"run.py"),"files":{f"{stage}-decisions-{i}.jsonl.gz":h for i,h in enumerate(hashes)}})
def evaluate(stage):
    sys.path.insert(0,str(OLD/"tail_read"))
    from tail import pilot,independent,compare
    truth=load(OLD/("write_transfer/gold-spans.json.gz" if stage=="dev" else "../graph_memory_round18/isetrace_official/gold-spans.json.gz"))
    seal=load(D/(stage+"-seal.json"));assert seal["model"]==sha(D/"model.json")
    arms=defaultdict(dict)
    for i,(filename,h) in enumerate(sorted(seal["files"].items())):
        assert sha(D/filename)==h
        with gzip.open(D/filename,"rb") as pred,gzip.open(inputs(stage,i)[0],"rb") as s:
            for pl,sl in zip(pred,s,strict=True):
                r,p=json.loads(sl),json.loads(pl);assert p["t"]==r["t"];ad=r["addresses"]
                nodes=[pilot.RankedNodeRecord(node_id=str(j),score=0,token_count=c,source_spans=(pilot.SourceSpan(event_id=ad[e][0],json_pointer=ad[e][1],char_start=a,char_end=b),)) for j,(e,a,b,c,_) in enumerate(r["blocks"])]
                for arm,(keep,group) in p["a"].items():
                    assert sum(nodes[j].token_count for j in keep)<=8192
                    for q,read in group.items():
                        gold=tuple(pilot.SourceSpan.model_validate(sp) for sp in truth[q])
                        for kind,picks,cap in (("archive",keep,8192),("read",read,2048)):
                            assert set(picks)<=set(keep)
                            sub=tuple(nodes[j] for j in picks);cost=sum(n.token_count for n in sub);assert cost<=cap
                            m=pilot.span_metrics_under_token_budget(sub,gold,cap)
                            alt=independent(truth[q],[n.model_dump() for n in sub])
                            assert all(abs(v-getattr(m,k))<1e-12 for v,k in zip(alt,("coverage","density","full_support"),strict=True))
                            k=kind+"/"+arm;assert q not in arms[k]
                            arms[k][q]={"t":r["t"],"tokens":cost,**{a:getattr(m,a) for a in ("full_support","coverage","density","f1")}}
    assert all(set(bits)==set(truth) for bits in arms.values())
    stats={k:{"hits":sum(bool(v["full_support"]) for v in rs.values()),**{a:mean(v[a] for v in rs.values()) for a in ("full_support","coverage","density","f1","tokens")}} for k,rs in arms.items()}
    pairs={}
    for kind in ("archive","read"):
        for a,b in (("set","frozen"),("mean","frozen"),("set","mean")):
            pairs[kind+"/"+a+"-"+b]=compare(arms[kind+"/"+a],arms[kind+"/"+b])
    save(D/(stage+"-results.json"),{"n":len(truth),"summary":stats,"pairs":pairs});save(D/(stage+"-outcomes.json.gz"),arms)
    print(stage,{k:v["hits"] for k,v in stats.items()},flush=True)
if __name__=="__main__":
    {"predict":predict,"score":evaluate}[sys.argv[1]](sys.argv[2])

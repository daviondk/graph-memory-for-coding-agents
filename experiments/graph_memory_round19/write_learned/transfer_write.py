"""Transfer the frozen writer and charge the model against the same byte allowance."""
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import gzip
import json
import os
import sys
from features import ROOT,ONLINE,TRAINED,load,save,sha,stream,binary
from forecast_write import choose
DEV=ROOT.parent/"write_transfer"
DEV_PROJ=stream.RUNTIME/"write-dev-private"/"projection"
def recent_projection(stage,i,t):
    return (DEV_PROJ if stage=="dev" else stream.CACHE)/f"{i}-{t}.json.gz"
def original(stage,i):
    return (DEV/f"predictions-{i}.jsonl.gz") if stage=="dev" else (ONLINE/f"forecast-{i}.jsonl.gz")
def storage(blocks,addresses,ids):
    es={blocks[k][0] for k in ids}
    return {"tokens":sum(blocks[k][3] for k in ids),"bytes":sum(binary.HDR.size+blocks[k][4] for k in ids)+sum(binary.EV.size+len(addresses[e][0].encode())+len(addresses[e][1].encode()) for e in es)}
def lock():
    src={n:sha(ROOT/n) for n in ("model.json","model-seal.json","forecast-seal.json","TRANSFER_RU.md","transfer_write.py")}
    source={n:sha(DEV/n) for n in ("design-lock.json","projection-lock.json","forecast-lock.json","split-audit.json","cohort.json")}
    dev=load(DEV/"cohort.json");train=load(ROOT/"train-evidence.json.gz")
    test=load(TRAINED/"split.json.gz")["test"];dt={r["t"] for r in dev};dq={r["q"] for r in dev}
    tq={q for r in train.values() for q in r["q"]}
    assert not dq & (tq|{r["q"] for r in test}) and not dt & (set(train)|{r["t"] for r in test})
    assert len(dq)==580 and len(dt)==352 and len(set(train))==256
    assert load(DEV/"split-audit.json")["sizes"]["train"]["t"]==2410
    assert (ROOT/"model.json").stat().st_size==3911
    save(ROOT/"transfer-plan.json",{"local":src,"dev_source":source,"train_test_dev_overlap":0,"paid_available":32768-3911})
def worker(task):
    stage,i=task;model=load(ROOT/"model.json");paid=load(ROOT/"transfer-plan.json")["paid_available"]
    with gzip.open(original(stage,i),"rb") as src,gzip.open(ROOT/f"transfer-{stage}-{i}.jsonl.gz","wt",encoding="utf8",compresslevel=3) as dst:
        for line in src:
            base=json.loads(line);t=base["t"]
            proj=load(recent_projection(stage,i,t));assert proj["t"]==t
            source=proj["fields"];ab=base["addresses"];blocks=base["blocks"]
            if stage=="dev":
                normal=choose(ab,blocks,source,proj["pool"],model)
            else:normal={}
            # No writer receives questions or labels. Only the budget is changed in this branch.
            oldcap=binary.CAP
            try:
                binary.CAP=paid
                cheaper=choose(ab,blocks,source,proj["pool"],model)["bytes/full"][0]
            finally:binary.CAP=oldcap
            modes={k:v[0] for k,v in normal.items()}
            modes["paid/full"]=cheaper
            if stage=="dev":
                counters=Counter();prior={"fifo":[],"output_head":[]};blob=[]
                for j,(e,p) in enumerate(ab):
                    es,ptr=e.encode(),p.encode();blob.append(binary.EV.pack(j,len(es),len(ptr))+es+ptr)
                for j,(e,l,r,c,n) in enumerate(blocks):
                    eid,ptr=ab[e]
                    prior["fifo"].append((-j,0));prior["output_head"].append((counters[e]*(2 if ptr=="/raw_arguments" else 1),stream.stable(eid)))
                    counters[e]+=1
                for k,keys in prior.items():
                    modes["bytes/"+k]=binary.select(blocks,keys,blob)[0]
                    modes["tokens/"+k]=base["arms"][k+"/8192"][0]
            # Content's index is reconstructed exclusively over retained blocks at read time.
            lex=[stream.content_tokens(source[ab[e][0]][a:b]) for e,a,b,_,_ in blocks]
            price=[b[3] for b in blocks];queries=[(q,stream.content_tokens(s)) for q,s in proj["q"]]
            forecast={}
            for name,ids in modes.items():
                read=stream.read(ids,price,lex,queries);st=storage(blocks,ab,ids)
                if name.startswith("paid/"):assert st["bytes"]+3911<=32768
                elif name.startswith("bytes/"):assert st["bytes"]<=32768
                else:assert st["tokens"]<=8192
                if name in ("tokens/fifo","tokens/output_head"):assert read==base["arms"][name.split("/")[1]+"/8192"][1]
                forecast[name]=[ids,read,st]
            dst.write(stream.dump({"t":t,"a":forecast})+"\n")
    dest=ROOT/f"transfer-{stage}-{i}.jsonl.gz";return dest.name,sha(dest)
def run():
    se=load(ROOT/"transfer-plan.json")
    assert all(sha(ROOT/n)==h for n,h in se["local"].items()) and all(sha(DEV/n)==h for n,h in se["dev_source"].items())
    dol=load(DEV/"forecast-lock.json")
    assert all(sha(DEV/f)==h for f,h in dol["forecasts"].items()) and dol["projections"]==sha(DEV/"projection-lock.json")
    for t,v in load(DEV/"projection-lock.json")["trajectories"].items():assert sha(recent_projection("dev",v["shard"],t))==v["projection_sha256"]
    assert all(sha(ONLINE/p)==h for p,h in load(ONLINE/"forecast-lock.json")["forecasts"].items())
    with ProcessPoolExecutor(3) as pool:pairs=list(pool.map(worker,[(stage,i) for stage in ("dev","test") for i in range(8)]))
    save(ROOT/"transfer-forecast-seal.json",{"design":sha(ROOT/"transfer-plan.json"),"forecasts":dict(pairs)})
    print("sealed",len(pairs),"files",flush=True)
if __name__=="__main__":{"lock":lock,"run":run}[sys.argv[1]]()

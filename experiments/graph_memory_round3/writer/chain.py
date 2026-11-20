import gzip,sys,itertools
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from replay import D,DATA,R2,read,save,old,rows,pages,order,Memory
sys.path.insert(0,str(D))
from score import locations,stats
import numpy as np
sys.path.insert(0,str(DATA))
from predict import at_cut
from context import prev
from policy import render, cost
from pipeline import future
def shard(k):
    origin=(read(R2/"span_memory/width_model.json"),read(R2/"edit_memory/model.json")["flat"],read(R2/"span_memory/offset.json")["intercept"])
    wm,ew,off=origin;model=read(DATA/"fine_model.json");model["lookup"]={k:j for j,k in enumerate(model["length_dist"])};model["cdfs"]=np.asarray(list(model["length_dist"].values()))
    with gzip.open(D/f"hybrid_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=2) as f:
        for obj in rows(DATA/f"source_{k}.jsonl.gz"):
            states={(a,b):Memory() for a in ("lru","point","typed") for b in (4096,12288)};cat={};cuts=[]
            for t,event in enumerate(obj["events"],1):
                for (a,b),m in states.items():m.step(event,t,a,b,obj,ew,wm,off)
                if t%4 or t>=len(obj["events"]):continue
                plans={}
                for (a,b),m in states.items():
                    rr=pages(m.state["rebase"]);idx=order(rr,m.meta)[:48]
                    result=at_cut(obj,t,rr,idx,m.meta,m.history,m.last,model,origin)[512]
                    resident={(p,lo+j):s for p,lo,hi,_,body in rr for j,s in enumerate(body.split("\n"))}
                    for mode in ("r2f","typed"):
                        selected,framed,wire=result[mode];runs=[];pieces=[]
                        for p,lo,hi in selected:
                            text="\n".join(resident[p,j] for j in range(lo,hi+1));key=(p,lo,hi,text)
                            if key not in cat:cat[key]=len(cat)
                            runs.append(cat[key]);pieces.append(f"@@ {p} {lo}..{hi} @@\n"+text)
                        assert cost("\n".join(pieces))==wire<=512 and sum(cost(s) for s in pieces)+max(0,len(pieces)-1)==framed<=512
                        plans[f"{a}/{mode}/{b}"]=[runs,wire]
                cuts.append([t,plans])
            f.write(__import__("json").dumps([obj["instance"],list(cat),cuts],separators=(",",":"))+"\n")
    return k
def grading():
    for n,s in read(D/"chain_lock.json").items():assert old.e.sha((D/n).read_bytes())==s
    allrows=[];count=0
    for k in range(8):
        src={r["instance"]:r for r in rows(DATA/f"source_{k}.jsonl.gz")}
        for snapshot,hybrid in zip(rows(D/f"sealed_{k}.jsonl.gz"),rows(D/f"hybrid_{k}.jsonl.gz"),strict=True):
            i,full,cuts,_=snapshot;i2,cat,preds=hybrid;assert i==i2
            for (t,w),(u,r) in zip(cuts,preds,strict=True):
                assert t==u;count+=1;q=future(src[i]["events"],t)
                if not q or not q[2]:continue
                gold=locations([full[x] for x in w["unbounded@0"]],q[0],q[1]);metrics={}
                for key,(ids,price) in r.items():
                    lines={n:s for j in ids for p,lo,hi,body in [cat[j]] if p==q[0] for n,s in enumerate(body.split("\n"),lo)};ms=[lines.get(n)==s for n,s in gold]
                    metrics[key]=[int(bool(ms) and all(ms)),float(sum(ms)/len(ms)) if ms else 0,price]
                allrows.append([i,t,metrics])
    with gzip.open(D/"hybrid_scores.jsonl.gz","wt",encoding="utf8") as f:
        for r in allrows:f.write(__import__("json").dumps(r,separators=(",",":"))+"\n")
    groups=[r[0].split(".")[0] for r in allrows];allv={key:np.array([r[2][key] for r in allrows]) for key in allrows[0][2]}
    summ={key:dict(whole=int(v[:,0].sum()),line_coverage=v[:,1].mean(),mean_tokens=v[:,2].mean()) for key,v in allv.items()}
    contrasts={}
    for b in (4096,12288):
        for a0,r0,a1,r1 in [("typed","typed","point","typed"),("typed","typed","lru","typed"),("typed","typed","typed","r2f"),("typed","typed","lru","r2f")]:
            s1=f"{a0}/{r0}/{b}";s2=f"{a1}/{r1}/{b}"
            contrasts[s1+" minus "+s2]=stats(allv[s1][:,0],allv[s2][:,0],groups)
    save(D/"chain_results.json",dict(n=len(allrows),cuts=count,arms=summ,contrast=contrasts))
def main():
    save(D/"chain_method_lock.json",{str(f):old.e.sha(f.read_bytes()) for f in [D/"CHAIN_PROTOCOL.md",D/"chain.py",D/"replay.py",D/"decision_lock.json",DATA/"predict.py",DATA/"fine_model.json",DATA/"context.py"]})
    with ProcessPoolExecutor(4) as pool:
        for k in pool.map(shard,range(8)):print("sealed chain",k,flush=True)
    files=[D/"chain_method_lock.json",*[D/f"hybrid_{k}.jsonl.gz" for k in range(8)]]
    save(D/"chain_lock.json",{p.name:old.e.sha(p.read_bytes()) for p in files})
    grading()
if __name__=="__main__":main()



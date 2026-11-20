"""Unchanged full-checkpoint writers under four additional budgets; no refitting or selection of points."""
import gzip,json,os,sys
from concurrent.futures import ProcessPoolExecutor
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
import writer as w
from writer import HERE,DATA,read,save,h,line,rows
import importlib.util
spec=importlib.util.spec_from_file_location('writer_grade_curve',HERE/'evaluate.py')
ev=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
from context import stream,future,line_target
B=(1024,2048,8192,24576)
C=HERE/"curve"
def run(k):
    w.HERE=C;w.BUDGETS=B
    return w.run(k)
def score(k):
    inp=iter(rows(C/f"cuts_{k}.jsonl.gz"));logs=iter(rows(C/f"events_{k}.jsonl.gz"));sc=[];cc=defaultdict(list);checks=0
    for obj in rows(DATA/f"source_{k}.jsonl.gz"):
        stats={}
        for t,_ in enumerate(obj["events"],1):
            i,st,records=next(logs);assert (i,st)==(obj["instance"],t);stats[t]={}
            for a,b,sha,sz,pre,removed,enc in records:
                assert sz<=b;cc[f"{a}@{b}"].append([sz,pre,removed,enc]);stats[t][a,b]=(sha,sz);checks+=1
        for t,rr,idx,meta,hist,last in stream(obj):
            i,tt,snap=next(inp);assert (i,tt)==(obj["instance"],t)
            q=future(obj["events"],t);target=q if q and q[2] else None
            loc=line_target(rr,target[0],target[1]) if target else None;g={}
            if loc:
                p,lo,hi,j=loc
                g={r[1]+off:s for r in rr if r[0]==p for off,s in enumerate(r[4].split("\n")) if lo<=r[1]+off<=hi};assert len(g)==hi-lo+1
            arms={}
            for a,b,sha,s in snap:
                buf=w.pack(s);assert t==s[1] and (h(buf),len(buf))==stats[t][a,b] and sha==h(buf)
                if target:
                    m=w.materialize(s)[1]["rebase"].get(target[0],{});matches=[m.get(z,[None])[0]==txt for z,txt in sorted(g.items())]
                    arms[f"{a}@{b}"]=[int(bool(matches) and all(matches)),sum(matches)/max(1,len(matches)),int(bool(matches) and matches[0])]
            if target:sc.append([i,t,len(g),arms])
    assert next(inp,None) is None and next(logs,None) is None
    return sc,cc,checks
def main():
    C.mkdir(exist_ok=True)
    P=[HERE/"writer.py",HERE/"CURVE_PROTOCOL.md",HERE/"curve.py",HERE/"method_lock.json",*sorted(DATA.glob("source_*.gz"))]
    save("curve_method_lock.json",{str(p):h(p.read_bytes()) for p in P})
    os.environ["OPENBLAS_NUM_THREADS"]="1"
    with ProcessPoolExecutor(4) as pool:ts=list(pool.map(run,range(8)))
    save("curve_timing.json",ts)
    save("curve_decision_lock.json",{str(p):h(p.read_bytes()) for p in [HERE/"curve_method_lock.json",*sorted(C.glob("cuts_*.gz")),*sorted(C.glob("events_*.gz"))]})
    with ProcessPoolExecutor(4) as pool:data=list(pool.map(score,range(8)))
    ss=[x for s,c,n in data for x in s];costs=defaultdict(list);checks=0
    with gzip.open(C/"scored.jsonl.gz","wt",encoding="utf8",compresslevel=4) as f:
        for s in ss:line(f,s)
    for s,c,n in data:
        checks+=n
        for a,v in c.items():costs[a].extend(v)
    base=read(HERE/"results.json");assert len(ss)==base["n"]==1210
    out={};comparisons={};groups=[r[0].split(".")[0] for r in ss]
    for b in sorted([*B,4096,12288]):
        temp={}
        for a in w.ARMS:
            key=f"{a}@{b}"
            if b in B:
                x=np.asarray([r[3][key] for r in ss]);temp[a]=x;meta=np.array(costs[key]);out[key]={"hits":int(x[:,0].sum()),"fraction":float(x[:,1].mean()),"starts":int(x[:,2].sum()),"max_bytes_all_checkpoints":int(meta[:,0].max()),"mean_bytes_all":float(meta[:,0].mean()),"evictions":int(meta[:,2].sum())}
            else:out[key]=base["arms"][key]
        for a in ("lru","point"):
            key=f"typed-{a}@{b}"
            comparisons[key]=ev.paired(temp["typed"],temp[a],groups) if b in B else base["comparisons"][key]
    result={"n":len(ss),"gold_in_unbounded_memory":sum(r[2]>0 for r in ss),"projects":len(set(groups)),"new_bound_checks":checks,"new_round_trip_checks":2424*len(w.ARMS)*len(B),"curves":out,"comparisons":comparisons}
    save("curve_results.json",result)
    for b in sorted([*B,4096,12288]):print(b,[out[f"{a}@{b}"]["hits"] for a in w.ARMS],flush=True)
if __name__=="__main__":main()


"""Freeze capture, numeric scores, hypotheses and six model-independent/targeted removals."""
from pathlib import Path
import hashlib
import sqlite3
import sys
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1]
sys.path.insert(0,str(W/"graph_memory_round28/logit_control"))
from control import plan as upstream,read,save,sha,pack,decode
PRIVATE=Path("D:/CodexResearch/x20-r29-multiban")
MODES=("full","pareto","range2d","top64")

def source():
    p,cases,_,pold,pnew=upstream()
    return p,cases,pold,pnew

def key(q,x):
    return hashlib.sha256((q+"|r29-multiple|"+str(x)).encode()).digest()

def arrays(db,ix):
    rows=db.execute("SELECT score,ord,lo,hi FROM r WHERE q=? ORDER BY score DESC,ord",(ix,)).fetchall()
    return tuple(np.asarray(col,dtype=dt) for col,dt in zip(zip(*rows),("f4","i4","i4","i4")))

def nonoverlap(x,y):
    return x[1]<=y[0] or y[1]<=x[0]

def capacity(intervals):
    count=0;high=None
    for l,h in sorted(intervals,key=lambda x:(x[1],x[0])):
        if high is None or l>=high:
            count+=1;high=h
    return count

def generate(q,records,lo,hi,kind):
    active=list(sorted(set(tuple(r[:2]) for r in records)))
    target=min(8,capacity(active));chosen=[]
    while len(chosen)<target:
        options=[]
        for item in active:
            others=[x for x in active if nonoverlap(x,item)]
            if len(chosen)+1+capacity(others)<target:continue
            mask=(lo>=item[0])&(hi<=item[1])
            if not np.any(mask):rank=len(lo)
            else:rank=int(np.flatnonzero(mask)[0])
            priority=(key(q,item),) if kind=="independent" else (rank,key(q,item))
            options.append((priority,item,others))
        assert options
        _,item,active=min(options,key=lambda x:x[0]);chosen.append(item)
    return {str(k):chosen[:k] for k in (2,4,8)}

def merge(bans):
    out=[]
    for l,h in sorted(bans):
        assert l<h
        if out and l<=out[-1][1]:out[-1]=(out[-1][0],max(out[-1][1],h))
        else:out.append((l,h))
    return out

def main():
    p,cases,old,new=source()
    proto={"parent":sha(W/"graph_memory_round28/logit_control/manifest.json"),"protocol":sha(D/"PROTOCOL_RU.md"),
           "scenario_code":sha(Path(__file__)),"ids":p["qids"],"timing_panel":p["panel"],"arms":MODES}
    oldplan=D/"plan.json"
    if oldplan.exists():assert read(oldplan)=={**proto,"arms":list(MODES)}
    else:save(oldplan,proto)
    dest=D/"scenarios.json.gz"
    db=sqlite3.connect(old/"full.sqlite");all_scenarios={}
    for ix,q in enumerate(p["qids"]):
        score,ordr,lo,hi=arrays(db,ix)
        rows=cases[q]["states"]["base"]["parts"]
        all_scenarios[q]={kind:generate(q,rows,lo,hi,kind) for kind in ("independent","targeted")}
        all_scenarios[q]["article"]=cases[q]["title"]
    save(dest,all_scenarios);db.close()
    save(D/"scenario-seal.json",{"input":sha(oldplan),"code":sha(Path(__file__)),"scenarios":sha(dest),"questions":len(all_scenarios)})
if __name__=="__main__":main()

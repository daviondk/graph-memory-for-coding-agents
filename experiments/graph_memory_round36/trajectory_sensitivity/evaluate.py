"""Reweight ISETrace histories and trim predetermined redundant-edge tails."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"): os.environ[key]="1"
import numpy as np

D=Path(__file__).resolve().parent
SRC=D.parent/"materialized_append"
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,data):
    b=json.dumps(data,sort_keys=True,separators=(",",":")).encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)

def panel(ids, rows):
    counts=np.array([[rows[t]["questions"],rows[t]["wins"],rows[t]["losses"]] for t in ids if rows[t]["questions"]])
    n,w,l=counts.T
    diff=w-l
    rng=np.random.default_rng(337036)
    qeffects,teffects=[],[]
    for _ in range(100):
        idx=rng.integers(len(n),size=(100,len(n)))
        qeffects.extend(100*diff[idx].sum(1)/n[idx].sum(1))
        teffects.extend(100*(diff/n)[idx].mean(1))
    graph=np.array([[rows[t]["never"],rows[t]["once"]] for t in ids])
    g=graph.sum(1)
    return {"all_histories":len(ids),"history_with_questions":len(n),"questions":int(n.sum()),
            "wins":int(w.sum()),"losses":int(l.sum()),"q_effect":100*diff.sum()/n.sum(),
            "q_ci":np.quantile(qeffects,[.025,.975]).tolist(),
            "equal_history_effect":100*(diff/n).mean(),"equal_history_ci":np.quantile(teffects,[.025,.975]).tolist(),
            "leave_one_out":[float(f(100*(diff.sum()-diff)/(n.sum()-n))) for f in (np.min,np.max)],
            "pooled_graph_share":float(graph[:,0].sum()/g.sum()),"zero_graphs":int((g==0).sum()),
            "nonzero_graph_share_quantiles":np.quantile(graph[g>0,0]/g[g>0],[.25,.5,.75]).tolist(),
            "never":int(graph[:,0].sum()),"once":int(graph[:,1].sum())}

def main():
    assert sha(SRC/"manifest.json")=="33cfd9168b28c67b8924f00a5b38abb1dba7a133ba282d9449ba624cb74c77b2"
    rows={}
    for i in range(8):
        for t,r in read(SRC/f"graphs-{i}.json.gz").items():
            s=r["states"]["50"]
            assert t not in rows and s["never_visible"]+s["once_visible"]==s["logical"]-s["exact"]
            rows[t]={"never":s["never_visible"],"once":s["once_visible"],"questions":0,"wins":0,"losses":0}
    for r in read(SRC/"outcomes.json.gz"):
        if r["cut"]!=50 or r["pilot"] or not r["eligible"]:continue
        x=rows[r["t"]];d=r["arms"]["M"][0]-r["arms"]["L"][0]
        x["questions"]+=1;x["wins"]+=int(d>0);x["losses"]+=int(d<0)
    assert len(rows)==1207 and sum(r["questions"] for r in rows.values())==901
    ids=sorted(rows,key=lambda t:(-rows[t]["once"]-rows[t]["never"],t))
    analyses={}
    for frac in (0,.01,.05,.10):
        drop=int(math.ceil(len(ids)*frac))
        analyses[str(frac)]=panel(ids[drop:],rows)
    save(D/"histories.json.gz",rows)
    save(D/"results.json",{"panels":analyses,"source_manifest":sha(SRC/"manifest.json"),
                     "per_history":sha(D/"histories.json.gz"),"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(Path(__file__))})
if __name__=="__main__":main()


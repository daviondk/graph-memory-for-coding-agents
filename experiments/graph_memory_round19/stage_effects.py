"""Retrospective decomposition of paired BM25 successes by survival under both writers."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
def audit(panel):
    keys=["both","full_only","rule_only","neither"]
    counts={k:dict(queries=0,full_read=0,rule_read=0,read_win=0,read_loss=0) for k in keys}
    clusters=collections.defaultdict(lambda:[0,0,0,0,0])
    for r in panel:
        w=r["a"]["tokens/full"]; c=r["a"]["tokens/output_head"]
        a,b=int(w[0]),int(c[0]); u,v=int(w[3]),int(c[3])
        assert u<=a and v<=b
        k={(1,1):"both",(1,0):"full_only",(0,1):"rule_only",(0,0):"neither"}[a,b]
        p=counts[k];p["queries"]+=1;p["full_read"]+=u;p["rule_read"]+=v
        p["read_win"]+=u>v;p["read_loss"]+=v>u
        clusters[r["t"]][keys.index(k)]+=u-v;clusters[r["t"]][-1]+=1
    arr=np.array(list(clusters.values()))
    rng=np.random.default_rng(13)
    stats=[]
    for _ in range(100):
        idx=rng.integers(0,len(arr),(100,len(arr)))
        sums=arr[idx].sum(axis=1)
        stats.extend(sums[:,:-1]/sums[:,-1,None])
    for k,v in counts.items():
        v["net"]=v["read_win"]-v["read_loss"]
        v["contribution_query_mean"]=v["net"]/len(panel)
        v["contribution_ci95"]=np.quantile(np.array(stats)[:,keys.index(k)],[.025,.975]).tolist()
    net=sum(x["net"] for x in counts.values())
    assert net==sum(int(r["a"]["tokens/full"][3])-int(r["a"]["tokens/output_head"][3]) for r in panel)
    return dict(n=len(panel),clusters=len(clusters),net=net,strata=counts)
def main():
    study=ROOT/"write_learned"
    out={}
    for label,file in [("test","outcomes.json.gz"),("dev","transfer-outcomes.json.gz")]:
        path=study/file
        rows=[x for x in json.loads(gzip.decompress(path.read_bytes())) if x.get("split",label)==label]
        assert len(rows)=={"dev":580,"test":2000}[label] and len(rows)==len({r["q"] for r in rows})
        out[label]=audit(rows);out[label]["source_sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
    (ROOT/"stage-effects.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print({k:{s:(m["queries"],m["net"]) for s,m in v["strata"].items()} for k,v in out.items()})
if __name__=="__main__":main()


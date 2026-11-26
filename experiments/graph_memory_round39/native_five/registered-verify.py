"""Independently rederive primary intervals from the fixed input matrix before and after completion."""
from pathlib import Path
import json,gzip,hashlib,sys
import numpy as np
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(mode):
    files=sorted(D.glob(mode+"-receipt-*.json"));rows={}
    for f in files:
        a=read(f);g=D/f"{mode}-{a['seed']}.json.gz"
        assert a["rows"]==sha(g) and a["plan"]==sha(D/"plan.json") and a["program"]==sha(D/"pipeline.py")
        r=read(g);assert len(r)==2000 and len({v[0] for v in r.values()})==1207;rows[a["seed"]]=r
    result=D/f"{mode}-complete.json"
    if result.exists():
        full=read(result)
        assert set(rows)=={13,17,29,37,41}
        for s,pack in [([13,17,29,37,41],full["five"]),([37,41],full["forward"])]:
            qs=sorted(rows[s[0]]);ts=[rows[s[0]][q][0] for q in qs];_,g=np.unique(ts,return_inverse=True);n=np.bincount(g)
            for index,arm in [(3,"full_rgcn"),(4,"wo_chunk_adjacency")]:
                diff=np.array([[rows[sid][q][1][0]-rows[sid][q][index][0] for q in qs] for sid in s]);b=np.stack([np.bincount(g,weights=d) for d in diff]);rs=np.random.default_rng(34092);rng=np.random.default_rng(34091);fixed=[];cross=[]
                for _ in range(100):
                    ids=rng.integers(len(n),size=(100,len(n)));den=n[ids].sum(1);test=np.stack([d[ids].sum(1)/den for d in b])
                    fixed.extend(test.mean(0));ss=rs.integers(len(s),size=(100,len(s)));cross.extend(test.T[np.arange(100)[:,None],ss].mean(1))
                ref=pack["comparisons"]["R35_oof_3894/"+arm]["full_support_2048"]
                np.testing.assert_allclose([ref["delta"],*ref["conditional_ci"],*ref["crossed_ci"]],[diff.mean(),*np.quantile(fixed,[.025,.975]),*np.quantile(cross,[.025,.975])],atol=1e-12,rtol=0)
        m=D/f"{mode}-manifest.json";assert all(sha(D/p)==v for p,v in read(m).items())
    return sorted(rows)
if __name__=="__main__":
    for k,v in read(D/"implementation.json").items():assert sha(D/k)==v
    assert sha(D/"plan.json")=="b6774b1837b126d8e17425856daf80b9149a81e39c29c216f94d295539303f34"
    print("Verified available matched seeds",{m:verify(m) for m in ("canonical","metric-matched")},flush=True)

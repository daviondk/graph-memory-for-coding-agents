"""Cross-check all five contrasts with index sampling, independently of multiplicity-weighted means."""
from pathlib import Path
import argparse,json,gzip,hashlib
import numpy as np
D=Path(__file__).resolve().parent
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check():
    meta=get(D/"inputs.json");res=get(D/"results.json");assert res["input"]==sha(D/"inputs.json")
    assert meta["plan"]==sha(D/"PROTOCOL_RU.md") and meta["program"]==sha(D/"measure.py")
    seeds=res["seeds"];assert seeds==[13,17,29];raw=[]
    for s in seeds:
        p=D/f"four-arms-{s}.json.gz";assert meta["rows"][str(s)]==sha(p);raw.append(get(p))
        a=get(D/f"checkpoint-audit-{s}.json")["checkpoint_audit"];assert all(v["dev_eval_queries"]==580 for v in a["graph"].values())
    qs=sorted(raw[0]);ts=[raw[0][q][0] for q in qs];assert all({q:x[q][0] for q in qs}==dict(zip(qs,ts)) for x in raw)
    _,groups=np.unique(ts,return_inverse=True);n=np.bincount(groups);assert len(qs)==2000 and len(n)==1207
    arr=np.array([[x[q][1:] for q in qs] for x in raw]);assert arr.shape==(3,2000,4,6)
    for i,name in enumerate(meta["models"]):np.testing.assert_allclose(arr[:,:,i,:].mean((0,1)),res["means"][name],atol=1e-12,rtol=0)
    for key,r in res["comparisons"].items():
        lhs,rhs=map(meta["models"].index,key.split("/"));y=arr[:,:,lhs,:]-arr[:,:,rhs,:]
        by=np.stack([[np.bincount(groups,weights=y[s,:,k]) for k in range(6)] for s in range(3)]).transpose(0,2,1)
        fix=[];cross=[];rg=np.random.default_rng(34091);rs=np.random.default_rng(34092)
        for _ in range(100):
            ix=rg.integers(1207,size=(100,1207));den=n[ix].sum(axis=1)[:,None]
            v=np.stack([by[j][ix].sum(axis=1)/den for j in range(3)])
            fix.extend(v.mean(0));pick=rs.integers(3,size=(100,3));cross.extend(v.transpose(1,0,2)[np.arange(100)[:,None],pick].mean(1))
        aa=np.quantile(fix,[.025,.975],axis=0);bb=np.quantile(cross,[.025,.975],axis=0)
        for j,m in enumerate(meta["metrics"]):
            z=r[m];np.testing.assert_allclose([z["delta"],*z["conditional_ci"],*z["crossed_ci"],*z["per_seed"]],
                    [y[:,:,j].mean(),*aa[:,j],*bb[:,j],*y[:,:,j].mean(1)],atol=1e-12,rtol=0)
def main():
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");a=p.parse_args();check()
    f=D/"manifest.json";h={p.name:sha(p) for p in D.iterdir() if p.is_file() and p!=f}
    if a.seal and not f.exists():f.write_text(json.dumps(h,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8",newline="\n")
    assert h==get(f);print("Verified 6,000 matched four-arm rows, all 30 effects and all joint intervals",sha(f))
if __name__=="__main__":main()

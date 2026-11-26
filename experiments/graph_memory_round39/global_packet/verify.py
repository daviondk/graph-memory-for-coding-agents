"""Verify per-query records and all stored means without loading model weights or torch."""
import gzip,hashlib,json,math
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    result=read(D/"results.json");nested=(D/"choose.cpp").exists();allrows={}
    for seed in result["seeds"]:
        k=f"test-{seed}";f=D/(k+"-outcomes.json.gz");v=read(f);scores=read(D/(k+"-scores.json"));pred=read(D/(k+"-pred.json.gz"))
        assert sha(f)==scores["outcomes"] and len(v)==2000 and len({x[0] for x in v.values()})==1207
        assert v.keys()==pred.keys()
        totals={}
        for q,(t,rows) in v.items():
            assert pred[q][0]==t
            if nested:rows={n+"/"+a:values for n,arms in rows.items() for a,values in arms.items()}
            for name,vals in rows.items():
                assert 0<=vals[1]<=1 and vals[0]==int(vals[1]==1) and vals[2]<=2048
                if name not in totals:totals[name]=[0.]*4
                for j,x in enumerate(vals):totals[name][j]+=x
        for a,sums in totals.items():
            calc=[x/2000 for x in sums];stored=result["per_seed"][str(seed)][a]
            assert all(math.isclose(u,vv,abs_tol=1e-9,rel_tol=0) for u,vv in zip(calc,stored))
            allrows.setdefault(a,[]).append(calc)
    for a,vs in allrows.items():
        for j in range(4):assert abs(sum(x[j] for x in vs)/len(vs)-result["means"][a][j])<1e-8
    for name,stats in result["contrasts"].items():
        a,b=name.split(" minus ")
        assert all(abs(x-y-z)<1e-8 for x,y,z in zip(result["means"][a],result["means"][b],stats["delta"]))
    if (D/"manifest.json").exists():
        for n,h in read(D/"manifest.json")["files"].items():assert sha(D/n)==h,n
    print("Verified",len(result["seeds"]),len(allrows),len(result["contrasts"]))
if __name__=="__main__":main()


"""Verify the local archive, emitted witnesses and all mean AUC values without model dependencies."""
from collections import Counter,defaultdict
from pathlib import Path
import json, gzip, hashlib, statistics, math
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def close(x,y):return math.isclose(x,y,abs_tol=1e-9)
def main():
    h=read(D/"manifest.json")
    for name,v in h.items():assert sha(D/name)==v,name
    assert set(h)=={p.name for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}
    b=read(D/"bounds.json");ws=read(D/"witnesses.json.gz");counts=defaultdict(lambda:[0]*5); pairs=defaultdict(Counter)
    for t,kind,local,low,high in ws.values():
        for label,y in (("low",low),("high",high)):
            for j,(a,z) in enumerate(zip(local,y)):
                assert a in (0,1) and z in (0,1)
                counts[kind,label][j]+=z; pairs[label][a-z]+=1
    for k,st in b["strata"].items():
        for label in ("low","high"):
            z=counts[k,label];v=[100*x/st["n"] for x in z]
            assert abs(statistics.mean(v)-st["mean"])<.005 and abs(statistics.stdev(v)-st["sample_sd"])<.005
            assert sum(z)==st["total_published"]
    for label,x in b["feasible_examples"].items():
        assert pairs[label][1]==x["wins"] and pairs[label][-1]==x["losses"]
    au=read(D/"auc.json");sums=defaultdict(lambda:[0.]*14);n=Counter(); qs=set();ts=set()
    for fn,hash_val,_ in au["parts"]:
        assert sha(D/fn)==hash_val;part=read(D/fn);assert qs.isdisjoint(part);qs.update(part)
        for row in part.values():
            ts.add(row["t"])
            for seed,methods in row["seeds"].items():
                for method,vals in methods.items():
                    for i in range(2):
                        curve=vals[2+i*6:8+i*6]
                        assert close(vals[i],(sum(curve)-(curve[0]+curve[-1])/2)/5)
                    for group in (("all5","seed13") if seed=="13" else ("all5",)):
                        key=(group,method);n[key]+=1
                        for j,a in enumerate(vals):sums[key][j]+=a
    assert len(qs)==2000 and len(ts)==1207 and qs==ws.keys()
    for group,panel in au["panels"].items():
        for method,expected in panel["means_pct"].items():
            key=(group,method); assert all(close(100*a/n[key],v) for a,v in zip(sums[key],expected))
    print(f"{len(h)} files; 2000 questions; 1207 trajectories; six-budget curves, empirical means and both possible pairings verified")
if __name__=="__main__":main()

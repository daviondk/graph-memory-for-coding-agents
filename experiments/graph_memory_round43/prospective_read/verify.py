"""Offline audits of repository isolation, realized scores, and a separate exact-cost oracle solver."""
import gzip,hashlib,json
from pathlib import Path

D=Path(__file__).resolve().parent
def read(n):
    b=(D/n).read_bytes();return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)
def sha(n):return hashlib.sha256((D/n).read_bytes()).hexdigest()

def independent_oracle(blocks,gain):
    head=[];used=0
    for j,b in enumerate(blocks):
        if used+b["cost"]>1024:break
        head.append(b["idx"]);used+=b["cost"]
    capacity=2048-used
    best={0:0}
    for b in blocks[len(head):]:
        credit=gain.get(str(b["idx"]),0)
        if not credit:continue
        old=list(best.items())
        for spent,val in old:
            new=spent+b["cost"]
            if new<=capacity:best[new]=max(best.get(new,0),val+credit)
    return sum(gain.get(str(j),0) for j in head)+max(best.values())

def main():
    fs=read("feature-seal.json");ranks=read("rank-seal.json");data=read("features.json.gz");obs=read("outcomes.json.gz")
    assert sha("PROTOCOL_RU.md")==fs["protocol"]==ranks["registered"] and sha("features.json.gz")==fs["features"]
    assert set(data)==set(obs) and len(data)==2696
    for repo,digest in ranks["folds"].items():
        tail=repo[:12];f="seal-"+tail+".json";assert sha(f)==digest
        anchor=read(f);held=read("ranks-"+tail+".json.gz");assert sha("ranks-"+tail+".json.gz")==anchor["rows"]
        assert repo==anchor["held_repo"] and {r for r,_,_ in anchor["train_files"]}==set(fs["repos"])-{repo}
        excluded=set()
        for other,fn,hashed in anchor["train_files"]:
            assert sha(fn)==hashed;part=read(fn);assert all(data[k]["repo"]==other for k in part);excluded.update(part)
        assert set(held).isdisjoint(excluded) and set(held)|excluded==set(data)
        y=read("labels-"+tail+".json.gz")
        for k,out in held.items():
            st=data[k];assert st["repo"]==repo and out["original"]==st["original"]
            rr=obs[k];gain=y[k]["matches"];bs=st["blocks"];idx={b["idx"]:b for b in bs}
            for m,seq in (out|{"oracle":rr["oracle_ids"]}).items():
                s=rr["scores"][m]
                assert len(seq)==len(set(seq)) and sum(idx[i]["cost"] for i in seq)==s["chosen_bytes"]<=2048
                assert s.get("lines",0)==sum(gain.get(str(i),0) for i in seq) and s["hit"]==int(s.get("lines",0)>0)
            assert independent_oracle(bs,gain)==rr["scores"]["oracle"].get("lines",0)
    z=read("results.json")
    assert sha("grade-seal.json")==z["grade"] and sha("outcomes.json.gz")==read("grade-seal.json")["rows"]
    for m,s in z["panels"]["all2696"]["methods"].items():
        for metric in ("lines","hit","chosen_bytes","nontarget_bytes"):assert s.get(metric,0)==sum(r["scores"][m].get(metric,0) for r in obs.values())
    if (D/"manifest.json").exists():
        for name,d in read("manifest.json")["files"].items():assert sha(name)==d,name
    print("Verified 5 disjoint repository forecasts, 2696 capacity-constrained episodes, oracle optima and printed totals.")

if __name__=="__main__":main()


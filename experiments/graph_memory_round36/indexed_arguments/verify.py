"""Independent standard-library audit of data identities, totals, schedules and aggregate cycles."""
from pathlib import Path
from collections import Counter
from hashlib import sha256
from statistics import mean,median
import gzip,json,math,itertools
D=Path(__file__).resolve().parent
def load(f):
    return json.loads(gzip.decompress(f.read_bytes()) if f.suffix==".gz" else f.read_bytes())
def sha(f):
    return sha256(f.read_bytes()).hexdigest()
def main():
    p=load(D/"plan.json");c=load(D/"count-seal.json");t=load(D/"timing-seal.json");r=load(D/"results.json")
    assert p["protocol"]==sha(D/"PROTOCOL_RU.md") and p["operator"]==sha(D/"indexed.py") and p["code"]==sha(D/"experiment.py")
    assert c["plan"]==t["plan"]==sha(D/"plan.json")
    prev=D.parent/"deferred_match";assert p["previous"]==sha(prev/"manifest.json")
    units=set();tot=Counter();cuts=0
    for f,h in c["files"].items():
        af=D/f;assert sha(af)==h
        old=load(prev/f.replace("audit-","counters-"))
        for tr,v in load(af).items():
            assert tr not in units;units.add(tr);cuts+=v["cuts"]
            a=v["counts"];b=old[tr]["counts"];tot.update(a)
            assert (a.get("all_predicates",0),a["events"],a["identity_integral"])==(b.get("predicate_old",0),b["event_checks"],b["observed_identity_integral"])
            assert a.get("raw_hits",0)+a.get("A_recursive_starts",0)==a.get("all_predicates",0)
            assert a.get("C_stored",0)<=a.get("B_stored",0) and a.get("C_leaf_substr_checks",0)<=a.get("A_B_leaf_substr_checks",0)
    assert r["counts"]==dict(tot) and (len(units),cuts)==(1207,4828)
    timed=load(D/"clock_samples.json.gz");assert t["data"]==sha(D/"clock_samples.json.gz")
    assert set(p["panel"])==set(timed)==set(sorted(units,key=lambda s:sha256(("R36-deferred-match-cpu|"+s).encode()).digest())[:96])
    orders=list(itertools.permutations("ABC"))
    for row in timed.values():
        assert len(row["samples"])==6 and sorted(orders[(j+row["schedule_shift"])%6] for j in range(6))==orders
    stats={}
    for i,k in enumerate(("cycles","cpu_ns","wall_ns")):
        means={m:[mean(rep[m][i] for rep in timed[q]["samples"]) for q in p["panel"]] for m in "ABC"}
        for left,right in (("C","A"),("B","A"),("C","B")):
            a,b=means[left],means[right];ratio=sum(a)/sum(b);label=left+"/"+right
            assert math.isclose(r["timing"][k][label]["ratio"],ratio)
            if k=="cycles":
                loo=[(sum(a)-x)/(sum(b)-y) for x,y in zip(a,b)]
                stats[label]=dict(faster_trajectories=sum(x<y for x,y in zip(a,b)),
                     median_trajectory_ratio=median(x/y for x,y in zip(a,b)),leave_one_out=[min(loo),max(loo)])
    result=dict(trajectories=len(units),events=tot["events"],cuts=cuts,timed_trajectories=len(timed),cycle_robustness=stats)
    (D/"independent.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf8");print(result)
if __name__=="__main__":main()

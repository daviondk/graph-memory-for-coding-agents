"""Independently audit predictions, numeric witness receipts, and observed pytest statuses."""
import collections
import gzip
import hashlib
import json
import re
from pathlib import Path
from statistics import mean
D=Path(__file__).resolve().parent
def load(name):
    f=D/name;b=f.read_bytes();return json.loads(gzip.decompress(b) if f.suffix==".gz" else b)
def hashit(b):return hashlib.sha256(b).hexdigest()
def words(text):return set(re.findall(r"[a-z0-9]+",re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",text).lower()))-{"test","tests","py","self"}
def main():
    for fn in ("design-lock.json","forecast-lock.json","execution-lock.json","MANIFEST_SHA256.json"):
        for path,digest in load(fn).items():assert hashit((D/path).read_bytes())==digest,(fn,path)
    f=load("forecasts.json.gz");rs=load("roster.json")["sites"];mem=load("memory.json.gz");actions=load("execution-receipts.json.gz")
    clean=load("clean-target.json.gz");matrix=load("exhaustive-matrix.json.gz");out=load("outcomes.json");s=load("summary.json")
    assert len(set(f))==len(rs)==s["n"] and set(f)==set(actions)==set(matrix)==set(out)
    for site in rs:
        k=site["id"];m=site["old"]["module"];guesses=f[k];ids=mem[m]["tests"];old=mem[m]["history"]
        assert all(mem[m]["statuses"][t]=={"native":"passed","observed":"passed"} for t in ids)
        names=words(site["old"]["function"]+" "+site["old"]["expression"])
        plain={tid:(len(names&words(tid))/len(names|words(tid)) if names|words(tid) else 0,idx) for idx,tid in enumerate(ids)}
        hit={t for t in ids if "predicate" in old[t].get(k,())};eq={t for t in ids if "equal" in old[t].get(k,())}
        reached={t for t in ids if "line" in old[t].get(k,())}
        def choose(s,t,u):
            if not ids:return None
            return max(ids,key=lambda n:(n in s,n in t,n in u,*plain[n]))
        assert guesses["pairs"]==choose(eq,hit,reached)
        assert guesses["reach"]==choose(set(),hit,reached) and guesses["line"]==choose(set(),set(),reached)
        assert guesses["lexical"]==choose(set(),set(),set()) and guesses["last"]==(ids[-1] if ids else None)
        for seed,guess in enumerate(guesses["placebo"]):
            order=sorted(hit,key=lambda n:hashit(f"{k}|{seed}|{n}".encode()))
            fake={order[j-1] for j in range(len(order)) if order[j] in eq}
            assert len(fake)==len(eq) and guess==choose(fake,hit,reached)
        for t,r in actions[k].items():
            assert r["target_clean"]==clean[m].get(t) and r["detected"]==(r["target_changed"]=="failed" and r["target_clean"]=="passed")
            if matrix[k]["error"] is None:assert matrix[k]["tests"].get(t)==r["target_changed"]
        for arm in ("pairs","reach","line","lexical","last"):
            assert out[k][arm]==int(bool(guesses[arm] and actions[k][guesses[arm]]["detected"]))
        assert out[k]["placebo"]==[int(bool(t and actions[k][t]["detected"])) for t in guesses["placebo"]]
    for arm,ct in s["counts"].items():assert sum(r[arm] for r in out.values())==ct
    scores=[sum(r["placebo"][seed] for r in out.values()) for seed in range(16)]
    assert scores==s["placebo_seed_counts"]
    assert s["paired"]["placebo"]["delta"]==(s["counts"]["pairs"]-mean(scores))/s["n"] or abs(s["paired"]["placebo"]["delta"]-(s["counts"]["pairs"]-mean(scores))/s["n"])<1e-12
    print("verified",s["n"],"changes,",s["native_unique_actions"],"unique isolated calls, 16 placebo rankings, all controls")
if __name__=="__main__":main()

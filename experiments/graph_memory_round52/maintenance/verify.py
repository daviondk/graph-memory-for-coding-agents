"""Verify seals, published estimates, temporal rank bounds and the bundled demonstration."""
import hashlib
import math
from pathlib import Path
import sqlite3
from source import ROOT,SOURCE,blocks,prepare,read,sha
from study import fixture
from replicate import replication_blocks

def counts(data):
    rows=changes=checks=steps=updates=0
    for e in data:
        xs=e["candidates"];before=None
        assert len({x[0] for x in xs})==len(xs)
        for t in range(e["cuts"]+1):
            top=max(((u if s is not None and s<=t else b,-r,-j) for j,r,b,u,s in xs))
            if before is None or top>before:rows+=1
            if before is not None:
                assert top>=before
                changes+=top[2]!=before[2];steps+=1;checks+=1+t
            before=top
        assert e["terminal"]==-before[2]
        updates+=len({x[4] for x in xs if x[4] is not None})
    assert rows<=len(data)+updates
    return rows,changes,checks,steps

def main():
    for seal in ("run-seal.json","replication-seal.json"):
        for path,digest in read(seal).items():assert sha((ROOT/path).read_bytes())==digest,path
    reg=read("registration.json")
    assert reg["workload"]==sha((ROOT/"workload.json.gz").read_bytes())
    a=read("workload.json.gz")
    if SOURCE.exists():
        assert sha(SOURCE.read_bytes())==reg["input"]
        assert prepare()==a
    assert len({e["digest"] for e in a})==len({e["q"] for e in a})==3840
    rows,changes,checks,steps=counts(a)
    for name,v in read("correctness.json").items():
        assert (changes,checks,steps)==(v["id_changes"],v["reads"],v["transactions"])
        if name=="journal":assert rows==v["history_rows"]
    fixture()
    for file,group_names in (("timings.json.gz",15),("frontier-timings.json.gz",16),("replication-timings.json.gz",3)):
        raw=read(file)
        reps=8 if file.startswith("replication") else 4
        assert len(raw)==group_names*reps and len({x["identity"] for x in raw})==1
        for x in raw:
            assert sorted(x["block_order"])==list(range(32))
            assert sorted(int(k) for k in x["blocks"])==list(range(32))
            assert all(elapsed>=w+r>=0 for elapsed,w,r in x["blocks"].values())
        for rep in range(reps):
            assert sorted(x["position"] for x in raw if x["rep"]==rep)==list(range(group_names))
        for plan,mode in {(x["plan"],x.get("reads",8)) for x in raw}:
            selected=[x for x in raw if x["plan"]==plan and x.get("reads",8)==mode]
            assert len(selected)==reps
            mean=sum(x["build_ns"]+x["checkpoint_ns"]+sum(b[0] for b in x["blocks"].values()) for x in selected)/reps/1e6
            reported=(read("replication.json")["plans"][plan]["ms"] if reps==8 else read("results.json")["modes"][str(mode)]["plans"][plan]["total_ms"])
            assert math.isclose(mean,reported)
    primary={q for ids in blocks(a) for q in ids};second={q for ids in replication_blocks(a) for q in ids}
    assert len(primary)==len(second)==1024 and primary.isdisjoint(second)
    db=sqlite3.connect(SOURCE.as_uri()+"?mode=ro&immutable=1",uri=True) if SOURCE.exists() else None
    import json
    demo=json.loads((ROOT/"demo"/"cases.json").read_text(encoding="utf-8"))
    by_id={e["q"]:e for e in a}
    for scene in demo.values():
        ep=by_id[scene["episode"]]
        assert ep["digest"]==scene["first_digest"]
        cand=[[x[k] for k in ("id","rank","base","boosted","seen")] for x in scene["candidates"]]
        assert cand==ep["candidates"]
        if db:
            from source import words
            fragment=db.execute("SELECT fragment FROM question WHERE panel=? AND q=?",(scene["panel"],scene["episode"])).fetchone()[0]
            title=next(x["title"] for x in scene["candidates"] if x["id"]==scene["target"])
            left,right=scene["witness"]
            assert words(fragment)[left-1:right]==words(title)
    if db:db.close()
    assert (ROOT/"demo"/"engine.py").read_bytes()==(ROOT/"engine.py").read_bytes()
    print(f"Verified {len(a)} episodes, {checks} as-of states, {rows} versions, 148 file-backed timing trials and three bundled traces.")
if __name__=="__main__":main()

"""Read-through memory with and without eviction, compared with shared retained events."""
import argparse
import hashlib
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from experiment import HERE, REPS, R56, aggregate, budget, check_digests, load, panels, prepare, run, save

SEED=57119
GROUP=("lru","lru_unbounded","shared")


def minimum_misses(ops,restart):
    before=set();after=set()
    n=sum(op[0]=="w" for op in ops)
    count=0
    for op in ops:
        if op[0]=="w":count+=1
        else:
            group=after if restart and count>=n//2 else before
            group.add(op[1])
    return len(before)+len(after)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    source=panels();inputs={};mins={};signatures={}
    for p in ("B","long"):
        for repo,stream in source[p].items():
            ops,key=prepare(stream,p);signatures[p+"/"+repo]=key
            inputs[p,repo]=ops,(budget(ops,False),budget(ops,True))
            for restart in (False,True):mins[p,repo,restart]=minimum_misses(ops,restart)
    assert signatures==load(R56/"durable/runs.json.gz")["oracle"]
    protocol=hashlib.sha256((HERE/"LRU_RU.md").read_bytes().replace(b"\r\n",b"\n")).hexdigest()
    path=HERE/"lru-runs.json.gz"; out=HERE/"lru-results.json"
    raw=load(path) if path.exists() else dict(seed=SEED,protocol=protocol,oracle=signatures,runs=[])
    assert raw["protocol"]==protocol and raw["oracle"]==signatures
    def verify_misses():
        for r in raw["runs"]:
            if r["mode"]=="lru_unbounded":
                misses=sum(1-q[-1] for q in r["queries"])
                assert misses==mins[r["panel"],r["repo"],r["restart"]]
    if args.verify:
        assert len(raw["runs"])==REPS*len(inputs)*2*len(GROUP)
        verify_misses();assert check_digests(raw)==18 and aggregate(raw,GROUP)==load(out)
        print("Verified 270 runs and unbounded LRU mandatory first misses.");return
    done={(r["panel"],r["repo"],r["restart"],r["mode"],r["rep"]) for r in raw["runs"]}
    rng=random.Random(SEED)
    with TemporaryDirectory(dir=HERE,prefix="lru-") as td:
        for rep in range(REPS):
            for (p,repo),(ops,budgets) in inputs.items():
                jobs=[(mid,mode) for mid in (False,True) for mode in GROUP]
                for pos,(mid,mode) in enumerate(rng.sample(jobs,len(jobs))):
                    if (p,repo,mid,mode,rep) in done:continue
                    db=Path(td)/"one.sqlite";r=run(ops,budgets[mid],db,mode,mid);db.unlink()
                    r.update(panel=p,repo=repo,restart=mid,mode=mode,rep=rep,position=pos)
                    raw["runs"].append(r)
            verify_misses();check_digests(raw);save(path,raw);save(out,aggregate(raw,GROUP))
            print("Unbounded LRU block",rep+1,"of",REPS,flush=True)


if __name__=="__main__":
    main()

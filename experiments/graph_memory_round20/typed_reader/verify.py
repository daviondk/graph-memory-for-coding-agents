"""Portable SHA, budget, per-query summaries and paired-count verifier for all experimental arms."""
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.name.endswith("gz") else b)
def dig(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b):
    assert abs(a-b)<1e-11,(a,b)
def check_rows(path):
    out=read(path/"outcomes.json.gz")
    z=read(path/"results.json")
    g=collections.defaultdict(dict)
    for r in out:
        assert 0<=r["tokens"]<=2048 and r["full_support"] in (0,1)
        assert r["nodes"]>=0 and 0<=r["coverage"]<=1 and 0<=r["density"]<=1
        k=r["arm"]+"/"+r["policy"];assert r["q"] not in g[k];g[k][r["q"]]=r
    for k,v in z["means"].items():
        rows=g[k]
        assert len(rows)==v["n"]==2000 and sum(r["full_support"] for r in rows.values())==v["hits"]
        for f in ("full_support","coverage","density","f1","tokens","nodes"):
            close(sum(r[f] for r in rows.values())/len(rows),v[f])
    for k,fields in z["pairs"].items():
        ab,pol=k.split("/");a,b=ab.split("-")
        for m,re in fields.items():
            v=[r[m]-g[b+"/"+pol][q][m] for q,r in g[a+"/"+pol].items()]
            assert re["win"]==sum(x>1e-13 for x in v) and re["loss"]==sum(x< -1e-13 for x in v)
            assert re["ties"]+re["win"]+re["loss"]==len(v)
            close(sum(v)/len(v),re["delta"])
    return len(out)
def all_files():
    return {str(p.relative_to(ROOT)).replace("\\","/"):dig(p) for p in ROOT.rglob("*")
            if p.is_file() and p!=ROOT/"MANIFEST_SHA256.json" and "__pycache__" not in p.parts}
def main():
    if (ROOT/"MANIFEST_SHA256.json").exists():assert all_files()==read(ROOT/"MANIFEST_SHA256.json")
    for base in (ROOT,ROOT/"train_bm25",ROOT/"mechanism/test-dev",ROOT/"mechanism/test-train"):
        e=read(base/"forecast-seal.json");assert e["q"]==2000 and e["t"]==1207
        assert all(dig(base/n)==h for n,h in e["forecasts"].items())
    n=sum(check_rows(p) for p in (ROOT,ROOT/"train_bm25",ROOT/"mechanism/test-dev",ROOT/"mechanism/test-train"))
    hold=ROOT/"holdout80"
    if (hold/"results.json").exists():
        f=read(hold/"forecast-seal.json")
        assert f["predictions"]==dig(hold/"forecasts.json.gz") and f["q"]==80 and f["t"]==74
        out=read(hold/"outcomes.json.gz");aggregate=read(hold/"results.json")
        novel=set(read(hold/"source-plan.json")["novel_trajectories"])
        for nm,z in aggregate.items():
            cohort,pol=nm.split("/")
            rr=[r for r in out if r["policy"]==pol and (cohort=="all" or ((r["t"] in novel)==(cohort=="novel")))]
            by=collections.defaultdict(dict)
            for r in rr:
                assert 0<=r["tokens"]<=2048 and r["q"] not in by[r["arm"]]
                by[r["arm"]][r["q"]]=r
            for a,v in z["means"].items():
                assert len(by[a])==v["n"]
                for m in ("full_support","coverage","density","f1","tokens","nodes"):
                    close(sum(r[m] for r in by[a].values())/len(by[a]),v[m])
            for key,fields in z["pairs"].items():
                a,b=key.split("-")
                if b!="dense":b=a.split("/")[0]+"/"+b
                for m,re in fields.items():
                    d=[r[m]-by[b][q][m] for q,r in by[a].items()]
                    close(sum(d)/len(d),re["delta"])
                    assert re["win"]==sum(x>1e-13 for x in d) and re["loss"]==sum(x< -1e-13 for x in d)
        n+=len(out)
    print("PASS. Native input seals; all stored arm/policy summaries and paired counts;",n,"scored rows.")
if __name__=="__main__":main()

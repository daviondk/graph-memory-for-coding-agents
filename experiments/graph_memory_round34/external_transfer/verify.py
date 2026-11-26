"""Check evidence hashes, source partitions and every published external mean without external packages."""
from pathlib import Path
from collections import defaultdict
import json,hashlib,gzip,math
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def same(a,b):return math.isclose(a,b,abs_tol=1e-10)
def check_means(rows,mu):
    for k,vs in mu.items():
        for j,v in enumerate(vs):
            assert same(sum(r["arms"][k][j] for r in rows.values())/len(rows),v),(k,j)
def main():
    h=read(D/"manifest.json")
    for name,v in h.items():assert sha(D/name)==v,name
    assert set(h)=={p.relative_to(D).as_posix() for p in D.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p!=D/"manifest.json"}
    orig=read(D/"features.json.gz"); by={k:{r["repo"] for r in orig.values() if r["split"]==k} for k in ("train","dev","test")}
    assert not by["train"]&by["dev"] and not by["train"]&by["test"] and not by["test"]&by["dev"]
    assert sum(map(len,by.values()))==171 and len(orig)==494
    for loc in (D,D/"strong"):
        inp=read(loc/"input.json");assert sha(loc/"features.json.gz")==inp["features"]
        s=read(loc/"seal.json");assert s["forecasts"]==sha(loc/"test-ranks.json.gz") and s["selection"]==sha(loc/"selection.json")
        assert s["code"]==sha(D/"experiment.py")
        data=read(loc/"features.json.gz");rs=read(loc/"test-ranks.json.gz");rows=read(loc/"test-outcomes.json.gz");v=read(loc/"results.json")
        assert len(rows)==214 and len({r["repo"] for r in rows.values()})==69 and sum(len(data[q]["ids"]) for q in rows)==18598
        assert rows.keys()==rs.keys()=={q for q,r in data.items() if r["split"]=="test"}
        assert 12840==v["native_checks"] and v["outcomes"]==sha(loc/"test-outcomes.json.gz")
        for q,r in rs.items():
            for ix in r.values():assert sorted(ix)==list(range(len(data[q]["ids"])))
        check_means(rows,v["means"])
    a=read(D/"ablation.json");raw=read(D/"ablation-outcomes.json.gz");check_means(raw,a["means"])
    for k,stats in a["effects_union_minus"].items():
        wins=sum(r["arms"]["union_cost"][0]>r["arms"][k][0] for r in raw.values())
        losses=sum(r["arms"]["union_cost"][0]<r["arms"][k][0] for r in raw.values())
        assert [wins,losses]==stats["wins_losses"]
    x=read(D/"alignment.json");r=read(D/"alignment-outcomes.json.gz");assert r.keys()==raw.keys() and len(x["per_seed_primary"])==64
    assert same(sum(v[2][0]-v[1][0] for v in r.values())/len(r),x["difference"][0])
    assert x["changed_states"]==59 and x["total_state_permutations"]==len(r)*64
    print(f"{len(h)} files, 494 states, split-disjoint 171 repositories, all means, 25,680 native checks recorded, 64 within-file-multiplicity permutations")
if __name__=="__main__":main()

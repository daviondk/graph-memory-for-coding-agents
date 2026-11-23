"""Verify sealed metrics with public metadata. Optional replay calls only four inspected author graders."""
import collections
import hashlib
import json
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(n):
    return json.loads((HERE/n).read_bytes())
def main():
    m=HERE/"MANIFEST_SHA256.json"
    if m.exists():
        idx=read(m.name)
        assert set(idx)=={p.name for p in HERE.iterdir() if p.is_file() and p!=m}
        assert all(hashlib.sha256((HERE/n).read_bytes()).hexdigest()==s for n,s in idx.items())
    x=read("surface-audit.json")
    assert x["full_git"]["commits"]==1 and x["public_tree"]["n_files"]==x["full_git"]["n_files"]==273
    assert x["full_git"]["output_prefix"]==[] and x["direct_e10"]["status"]==404
    assert x["refs"]["count"]==1 and not x["releases"]["count"] and not x["tags"]["count"]
    e=read("e4-reconstruction.json")
    assert e["n"]==len(set(e["queries"]))==sum(e["mode_counts"].values())==500
    for arm,metrics in e["statistics"].items():
        z=metrics["full_support"]
        hits=round(500*z["full_500"])
        assert abs(z["unknown_469_lower"]-max(0,hits-31)/469)<1e-12
        assert abs(z["unknown_469_upper"]-min(469,hits)/469)<1e-12
    decisions=read("downstream-decisions.json")
    results=read("downstream-results.json")
    plan=read("downstream-plan.json")
    assert len(plan["tasks"])==len(decisions)==len(results["rows"])==24
    s={r["key"]:r for r in decisions}
    ids={r["key"] for r in plan["tasks"]}
    assert ids==set(s)=={r["key"] for r in results["rows"]} and len(ids)==24
    arms=collections.defaultdict(list)
    for r in results["rows"]:
        d=s[r["key"]]
        assert r["task"]==d["task"] and r["arm"]==d["arm"] and r["swap"]==d["swap"]
        chosen=d["selected"]
        assert r["passed"]==(results["controls"][d["task"]][chosen] if chosen else False)
        arms[r["arm"]].append(int(r["passed"]))
    print("PASS. 500 E4 pre-audit IDs, 3 partial-identification envelopes, 24 decisions with author checker.",{a:sum(v) for a,v in arms.items()})
    if "--replay" in sys.argv:
        import downstream as dx
        sys.path.insert(0,str(dx.REPO))
        for r in results["rows"]:
            d=s[r["key"]]
            ok,why=dx.check(r["task"],d["selected"]) if d["selected"] else (False,None)
            assert ok==r["passed"] and why==r["checker_result_hash"]
        print("PASS. All 24 selected actions independently replayed on author evaluator.")
if __name__=="__main__":
    main()

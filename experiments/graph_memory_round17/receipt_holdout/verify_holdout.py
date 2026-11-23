"""Digest and JUnit audit over all runs, preserving skipped selections separately from positive receipts."""
import collections
import hashlib
import json
from verify import ROOT,read,verify_run

def main():
    for name in ("rollback-lock.json","rollback-forecast-seal.json","testmon-forecast-seal.json"):
        for n,h in read(name).items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    for n,h in read("replication-lock.json")["source_hashes"].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    for n,h in read("testmon-assignment.json")["hashes"].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    assert read("collection-audit.json")["updated_hash"]==hashlib.sha256((ROOT/"rollback-roster.json").read_bytes()).hexdigest()
    regs=read("testmon-warm.gz");sel={r["commit"]:r for r in read("testmon-runs.gz")};graph=read("graph-actions.gz")
    counts=collections.Counter();unique_names=set();false_g=[];false_t=[]
    for c,a in regs.items():
        old=verify_run(a["pure_child"]);assert old==verify_run(a["warm"])==verify_run(graph[c]["initial"])
        untouched=verify_run(a["unchanged"])
        b=sel[c];actual=verify_run(b["replay"][0]);assert actual==verify_run(b["replay"][1]) and set(actual)==set(old)
        tm=verify_run(b["selected"]);g=verify_run(graph[c]["final"]) if graph[c]["final"] else {}
        assert all(actual[k]==v for k,v in g.items()) and all(actual[k]==v for k,v in tm.items())
        ok={k for k,v in old.items() if v=="pass"}
        assert all(v!="pass" or k not in ok for k,v in untouched.items())
        assert ok|set(graph[c]["no_receipt"])==set(old)
        counts.update({"n_cold":len(old),"n_eligible":len(ok),"positive_unchanged_called":len(ok&untouched.keys()),"all_unchanged_called":len(untouched),"graph_positive_called":len(ok&g.keys()),"native_positive_called":len(ok&tm.keys()),"all_graph_called":len(g),"all_native_called":len(tm),"failures":sum(actual[k]=="fail" for k in ok)})
        false_g.extend((c,k) for k in ok if actual[k]=="fail" and k not in g)
        false_t.extend((c,k) for k in ok if actual[k]=="fail" and k not in tm)
        unique_names.update(ok)
    cohorts={r["commit"]:r for r in read("rollback-roster.json")["blocks"]};baseline={c["commit"]:c for c in json.loads((ROOT.parent/"receipt_invalidation/rollback-roster.json").read_bytes())["blocks"]}
    assert not {r[k] for r in cohorts.values() for k in ("commit","parent")} & {r[k] for r in baseline.values() for k in ("commit","parent")}
    primary={r["name"] for b in baseline.values() for r in b["tests"]}
    current={r["name"] for b in cohorts.values() for r in b["tests"]}
    result={"counts":counts,"false_graph":false_g,"false_testmon":false_t,"overlap_method_names_with_primary":sorted(primary&current),"n_unique_holdout_names":len(current),"source_sha_overlap":0}
    (ROOT/"verification.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(result)
if __name__=="__main__":main()

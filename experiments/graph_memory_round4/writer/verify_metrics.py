"""Recount each published score, check pre-evaluation hashes, and validate disjoint panels."""
from collections import Counter
from pathlib import Path
from shared import D,A,B,read,rows,sha,save
def check_scores(file,expected):
    data=list(rows(file));assert data
    arms=list(data[0][-1]);n=len(data);length=len(set((r[0], r[2]) for r in data))
    assert n==length
    for a in arms:
        hits=sum(q[-1][a][0] for q in data);rc=expected[a]
        if isinstance(rc,dict):
            assert hits==rc["full"] and sum(q[-1][a][2] for q in data)==rc["start"]
            assert abs(sum(q[-1][a][1] for q in data)/n-rc["fraction"])<1e-10
        else:assert hits==rc
    return {"rows":n,"methods":arms}
def main():
    checks={}
    for name in "ABC":
        p=D/("panel_"+name);checks["primary_"+name]=check_scores(p/"scored.jsonl.gz",read(p/"results.json")["arms"])
        q=D/("ablation_"+name);exp=read(D/"ablation_results.json")[name]["arms"]
        checks["ablation_"+name]=check_scores(q/"scored.jsonl.gz",{a:r[0] for a,r in exp.items()})
    for arm in "AB":
        p=D/"anchor"/arm;checks["anchor_"+arm]=check_scores(p/"scored.jsonl.gz",read(D/"anchor/results.json")[arm]["full"])
    checks["anchor_C"]=check_scores(D/"anchor/C/scored.jsonl.gz",read(D/"anchor/C/results.json")["full"])
    for name in ["writer","anchor"]:
        q=D/"source_kimi"/name;checks["Kimi_"+name]=check_scores(q/"scored.jsonl.gz",read(D/"source_kimi/results.json")[name]["arms"])
    for name,c in read(D/"anchor/factorial/results.json").items():
        checks["factorial_"+name]=check_scores(D/"anchor/factorial"/name/"scored.jsonl.gz",c["counts"])
    keys=lambda p:{r["instance_id"] for r in read(p/"selection.json")}
    assert not keys(A)&keys(B) and not (keys(A)|keys(B))&keys(D)
    assert keys(D/"source_kimi")<=keys(A)|keys(B)
    locks=[D/"freeze.json",D/"anchor/C/method_lock.json",D/"source_kimi/method_lock.json"]
    for p in locks:
        lock=read(p);values=lock.get("inputs") or lock["files"]
        assert all(sha(Path(n))==v for n,v in values.items())
    assert read(D/"candidate_lock.json")["name"]==read(D/"freeze.json")["candidate"]
    src=read(D/"source_kimi/audit_display.json")["totals"];assert src["projected"]==src["found"]
    save(D/"verified_metrics.json",dict(checked=checks,disjoint_primary=True,shared_issues_other_agent=len(keys(D/"source_kimi")),scoring_locks=len(locks)))
    print(len(checks),"panels/experiments rechecked; links and freezes passed")
if __name__=="__main__":main()

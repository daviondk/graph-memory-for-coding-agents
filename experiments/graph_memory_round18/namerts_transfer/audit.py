"""Verify seals, score secondary panels, and retain all item identities before/after."""
import json
import platform
import sys
from plan import ROOT,PKG,OLD,VERSION,git,load,put,sha
from score import FILES,combine,table

def check_seal(filename):
    hashes=load(ROOT/filename)
    assert all(sha((ROOT/n).read_bytes())==h for n,h in hashes.items()),filename

def states(run):
    by_id={}
    for node,phase,status in (run.get("runtime") or {}).get("outcomes",[]):
        by_id.setdefault(node,{})[phase]=status
    return by_id

def pair_outcomes(before,after,truth):
    b,a=states(before),states(after)
    both=b.keys() & a.keys()
    passed={k for k,s in b.items() if s.get("call")=="passed" and "failed" not in s.values()}
    recovered={k for k in both if k in passed and a[k].get("call")=="passed" and "failed" not in a[k].values()}
    fail={k for k in both if k in passed and "failed" in a[k].values()}
    return {"current":before["current"],"file":before["file"],"author_affected":truth,"baseline_clean":before["clean"],
       "current_clean":after["clean"],"before_items":len(b),"after_items":len(a),"old_pass":len(passed),
       "common_item_ids":len(both),"confirmed_same_pass":len(recovered),"pass_to_fail":sorted(fail),
       "pass_to_skip_or_incomplete":sorted((passed & both) -recovered-fail),
       "new_only":sorted(a.keys()-b.keys()),"old_only":sorted(b.keys()-a.keys()),
       "any_outcome_change_common":sorted(k for k in both if b[k]!=a[k]),"wall_after_s":after["wall_s"]}

def main():
    for seal in ("plan-lock.json","forecast-seal.json","frequency-lock.json","frequency-seal.json"):
        check_seal(seal)
    plan=load(ROOT/"plan.json");old=set(plan["old_shas"]);new=plan["cohort"]
    assert all(not (old & {p["true_parent"],p["direct_parent"],p["current"]}) for p in new)
    forecasts=load(ROOT/"forecasts.gz");prior=load(ROOT/"paired.json")
    assert len({(r["current"],r["file"]) for r in forecasts})==len(forecasts)==120
    for pair in new:
        assert len(pair["pool"])==48
        pred={r["file"] for r in forecasts if r["current"]==pair["current"]}
        assert pred==set(pair["tests"])
    authors={k:{row["current"]:row for row in json.loads(git("show",VERSION+":"+p,where=PKG)) if row.get("target",True)} for k,p in FILES.items()}
    plan_extra=load(ROOT/"supplemental-plan.json");extra=load(ROOT/"supplemental-forecasts.gz")
    pairs=combine(plan_extra,extra,authors)
    put(ROOT/"supplemental-results.json",{"pairs":pairs,"aggregate":table(pairs) if pairs else {},
        "clean":sum(r["clean"] for r in extra),"base_item_passes":sum(r["passes"] for r in extra),
        "sum_wall_s":sum(r["wall_s"] for r in extra)})
    after=load(ROOT/"current-actual.gz")
    inputs={(r["current"],r["file"]):r for r in forecasts}
    truth={p["current"]:set(p["truth"]) for p in prior}
    assert {(r["current"],r["file"]) for r in after}=={(p["current"],f) for p in new for f in p["tests"][:3]}
    rows=[pair_outcomes(inputs[r["current"],r["file"]],r,r["file"] in truth[r["current"]]) for r in after]
    put(ROOT/"current-diagnostic.json",rows)
    ret={k:sum((len(r[k]) if isinstance(r[k],list) else r[k]) for r in rows) for k in
         ("author_affected","current_clean","before_items","after_items","old_pass","common_item_ids","confirmed_same_pass",
          "pass_to_fail","pass_to_skip_or_incomplete","new_only","old_only","any_outcome_change_common","wall_after_s")}
    freq=load(ROOT/"mechanism-frequency.json")
    verification={"roster_candidates":len(freq),"old_new_sha_overlap":0,"unique_primary_base_revisions":len({r["true_parent"] for r in new}),
        "check_seals":"verified","primary_forecasts":len(forecasts),"eligible_owner_gains_before_global":sum(bool(r["gains"]) for r in freq),
        "eligible_owner_gains_after_global":sum(r["eligible"] for r in freq),"new_supplemental_forecasts":len(extra),
        "actual_repeat_fields":ret}
    put(ROOT/"verification.json",verification);print(verification,flush=True)
if __name__=="__main__":main()

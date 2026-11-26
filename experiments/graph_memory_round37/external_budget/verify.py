from threshold import *
import math
def main():
    p=load(D/"plan.json");a=load(D/"audit.json");d=load(D/"thresholds.json.gz");j=load(D/"results.json");qs=sorted(d);z=load(D/"quota-examples.json");assert p["protocol"]==sha(D/"PROTOCOL_RU.md") and p["program"]==sha(D/"threshold.py") and p["source_manifest"]==sha(R/"manifest.json")
    for f,h in p["inputs"].items():assert sha(R/f)==h
    assert a["registered"]==sha(D/"plan.json") and j["thresholds"]==a["thresholds"]==z["all_inputs_sha"]==sha(D/"thresholds.json.gz") and j["code"]==sha(D/"analysis.py")
    n=len(d);assert n==214 and len({r["repo"] for r in d.values()})==69
    for k in METHODS:
        old=j["arms"][k]
        cut=[min(r["arms"][k]["cost8"] if r["arms"][k]["cost8"] is not None else 6144,6144) for r in d.values()]
        assert math.isclose(sum(cut)/n,old["restricted_cost"])
        for i,B in enumerate(BUD):
            valid=sum(v["arms"][k]["cost8"] is not None and v["arms"][k]["cost8"]<=B for v in d.values());assert valid==old["budget_counts"][i]["mss"]
    for row in d.values():
        for arm in row["arms"].values():
            if arm["cost8"] is not None:assert arm["cost8"]==arm["outside_tokens"]+arm["cert_eligible_tokens"] and arm["rank8"]<=8
    cases=[r for r in z["win_finite_both_multigroup_by_budget"]["2048"] if r["rank_same"]];assert len(cases)==1
    assert z["both_finite"]==95 and z["both_finite_different_certificate_union_token_cost"]==0
    mm=D/"manifest.json"
    if "--seal" in sys.argv:save(mm,{"algorithm":"SHA-256","files":{v.name:sha(v) for v in sorted(D.iterdir()) if v.is_file() and v!=mm}})
    files=load(mm)["files"];assert set(files)=={v.name for v in D.iterdir() if v.is_file() and v!=mm};assert all(sha(D/k)==h for k,h in files.items());print(len(files),"verified files",sha(mm))
if __name__=="__main__":main()

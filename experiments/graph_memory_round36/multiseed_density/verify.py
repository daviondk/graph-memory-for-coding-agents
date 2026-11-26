from summarize_density import *
import sys
def main():
    p=load(D/"plan.json");f=load(D/"forecast-seal.json");a=load(D/"outcome-audit.json");b=load(D/"results.json");out=load(D/"outcomes.json.gz");mid=load(D.parent/"multiseed_midpoint/outcomes.json.gz");shs=D.parent/"edge_count_control";real=load(D/"sensitivity.json");primary=b["panels"]["primary"]
    assert sha(shs/"manifest.json")==p["count"] and sha(D.parent/"multiseed_midpoint"/"forecast-seal.json")==p["mid_forecast"] and sha(D.parent/"multiseed_midpoint"/"outcomes.json.gz")==p["mid_outcomes_sha"]
    assert p["code"]==sha(D/"predict_density.py") and p["protocol"]==sha(D/"PROTOCOL_RU.md") and a["code"]==sha(D/"score_density.py") and b["script"]==sha(D/"summarize_density.py")
    assert f["plan"]==sha(D/"plan.json") and a["forecast"]==sha(D/"forecast-seal.json") and a["outcomes"]==b["outcomes"]==sha(D/"outcomes.json.gz")
    for n,h in f["files"].items():assert sha(D/n)==h
    assert set(out)==set(mid) and f["audit"]=={"anchors":24000,"delta_hashes":22933,"draws":19312,"histories":1207,"old13":38000,"q":2000} and a["anchors"]==24000
    sums=np.zeros((5,3));n=0
    for q,x in out.items():
        val=np.array(x["values"]);assert x["t"]==mid[q]["t"] and x["pilot"]==mid[q]["pilot"] and x["eligible"]==mid[q]["eligible"]
        for s in SEEDS:
            ix=x["seeds"][str(s)];e,m,l=val[ix[:3]]
            for j,k in enumerate(["E","M","L"]):assert val[ix[j],:2].tolist()==mid[q]["seeds"][str(s)][k]
            if not x["eligible"] or x["pilot"]:continue
            gr=val[ix[3:11]].mean(axis=0);tr=val[ix[11:]].mean(axis=0);sums+=np.stack([m-gr,m-tr,m-l,gr-l,tr-l]);n+=1
    assert n==901*4 and np.allclose(primary["delta"],sums*np.array([100,100,1])/n,atol=1e-11)
    assert primary["choice_support"]["global_choice"]["questions"]==real["G"]["conditional_on_possible_redraw"]["q"]
    mm=D/"manifest.json"
    if "--seal" in sys.argv:save(mm,{"algorithm":"SHA-256","files":{z.name:sha(z) for z in sorted(D.iterdir()) if z.is_file() and z!=mm}})
    signed=load(mm)["files"];assert set(signed)=={z.name for z in D.iterdir() if z.is_file() and z!=mm};assert all(sha(D/nm)==h for nm,h in signed.items());print(len(signed),"verified files",sha(mm))
if __name__=="__main__":main()

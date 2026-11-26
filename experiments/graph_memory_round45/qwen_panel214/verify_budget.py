"""Independent arithmetic check for bounded-budget AUC, all fixed budget counts and expenses."""
from itertools import accumulate
from math import isclose
from verify import get,sha
from verify_metrics import scores
def main():
    res=get("budget-results.json");g=get("cal-ordinal-judgments.json.gz");data=get("budget-thresholds.json.gz");panel=get("panel.json");b=res["budgets"]
    assert sha("budget-thresholds.json.gz")==res["thresholds"] and sha("audit-seal.json")==res["checks"] and sha("BUDGET_AUDIT_RU.md")==res["protocol"]
    M=res["M"];count=0
    for name,src in (("base","predictions.json.gz"),("fusion","fusion-predictions.json.gz")):
        for q,rows in get(src).items():
            unit=g[q];index={k:j for j,k in enumerate(unit["ids"])}
            for m,arr in rows.items():
                pred=[index[e] for e in arr];r=data[q][name+"/"+m];edges=list(accumulate(unit["cost"][e] for e in pred))
                tested=[scores(pred[:j],unit)[0] for j in range(9)]
                assert tested==sorted(tested)
                target=([0]+edges)[tested.index(1.0)] if any(tested) else None
                assert target==r["threshold"]
                area=sum(max(0,min(M,z)-min(M,y))*ok for y,z,ok in zip([0]+edges,edges+[max(M,edges[-1])],tested))
                assert isclose(area/M,r["auc"],abs_tol=1e-14)
                for j,cap in enumerate(b):
                    n=sum(e<=cap for e in edges);assert r["use"][j]==([0]+edges)[n] and r["hit"][j]==tested[n]
                count+=1
    for name,qs in (("outside204",panel["remaining"]),("all214",panel["order"])):
        for m,vals in res["panels"][name]["methods"].items():
            assert vals["counts"]==[sum(data[q][m]["hit"][i] for q in qs) for i in range(len(b))]
            assert isclose(vals["auc"],sum(data[q][m]["auc"] for q in qs)/len(qs),abs_tol=1e-12)
    print("Verified integrals by summing step heights, cost and count curves for",count,"rankings.")
if __name__=="__main__":main()

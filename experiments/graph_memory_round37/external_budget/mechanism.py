"""Describe equally ranked group quotas and cost-only switches using read-only artifacts."""
from threshold import *
def main():
    out=load(D/"thresholds.json.gz");bins={};both=[]
    for q,r in out.items():
        a,b=(r["arms"][m] for m in METHODS[:2])
        if a["cost8"] is not None and b["cost8"] is not None:both.append([q,a["cert_eligible_tokens"]-b["cert_eligible_tokens"]])
    for i,k in enumerate(BUD):
        changes=[]
        for q,r in sorted(out.items()):
            a,b=(r["arms"][m] for m in METHODS[:2])
            if a["budgets"][i][0] or not b["budgets"][i][0]:continue
            if len(r["group_quota"])<2 or a["cost8"] is None or b["cost8"] is None:continue
            changes.append({"q":q,"repo":r["repo"],"task":r["task"],"quota":r["group_quota"],"rank_same":a["group_ranks"]==b["group_ranks"] and a["alternate_ranks"]==b["alternate_ranks"],"arms":{m:{s:r["arms"][m][s] for s in ["rank8","cost8","group_ranks","alternate_ranks","cert_eligible_tokens","outside_tokens","head"]}|{"group_recall":r["arms"][m]["budgets"][i][1],"observed_depth":r["arms"][m]["budgets"][i][5]} for m in METHODS[:2]}})
        bins[str(k)]=changes
    save(D/"quota-examples.json",{"both_finite":len(both),"both_finite_different_certificate_union_token_cost":sum(k!=0 for q,k in both),"win_finite_both_multigroup_by_budget":bins,"all_inputs_sha":sha(D/"thresholds.json.gz")})
if __name__=="__main__":main()

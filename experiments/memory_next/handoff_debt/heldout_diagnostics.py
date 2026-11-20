"""Post-score diagnostics of cumulative input differences and the published receiver-only control."""
from collections import defaultdict
import json,random
from statistics import mean,median
from score import ROOT,readrows,result,VIEWS,quantile

def run():
    fit=json.loads((ROOT/"fit.json").read_text(encoding="utf-8"))
    train=[r for r in readrows("assignments.csv") if r["instance"] in set(fit["train_ids"])]
    available={r["run_id"]:r for r in readrows("arm_outcomes.csv")}
    recv=[r for r in train if r["succ"]=="qwen"]
    def rate(rs,v):return mean(result(available[r[v]],"success") for r in rs)
    posterior={v:(len(recv)*rate(recv,v)+20*rate(train,v))/(len(recv)+20) for v in VIEWS[:-1]}
    pref=["raw_trace","structured_notes","summary_notes","repo_only"]
    arm=max(pref,key=lambda v:posterior[v])
    assignments=readrows("heldout_predictions.csv")
    assert all(r["receiver"]==arm for r in assignments)
    observed={r["run_id"]:r for r in readrows("heldout_outcomes.csv")}
    cost={}
    for p in ["stage16","lead20"]:
        groups=defaultdict(list)
        for r in assignments:
            a=result(observed[r[r[p]]],"prompt_tokens");b=result(observed[r["raw_trace"]],"prompt_tokens")
            if a is not None and b is not None:groups[r["instance"]].append((a-b,b))
        allpairs=[x for vals in groups.values() for x in vals];vals=[d for d,base in allpairs];n=len(vals)
        cp=[(sum(d for d,b in v),len(v)) for v in groups.values()];rng=random.Random(16112026);samples=[]
        for _ in range(10000):
            s=rng.choices(cp,k=len(cp));samples.append(sum(d for d,n in s)/sum(n for d,n in s))
        cost[p]={"pairs":n,"tasks":len(cp),"mean_difference":mean(vals),"median_difference":median(vals),
                 "mean_raw":mean(b for d,b in allpairs),"fractional_difference":sum(vals)/sum(b for d,b in allpairs),
                 "lower":sum(x<0 for x in vals),"higher":sum(x>0 for x in vals),"same":sum(x==0 for x in vals),
                 "ci95_mean_difference":[quantile(samples,.025),quantile(samples,.975)]}
    return {"receiver_only_20":arm,"receiver_only_probabilities":posterior,"identical_to_model_constant":True,"input_tokens_vs_raw":cost}
if __name__=="__main__":
    ans=run();(ROOT/"heldout_diagnostics.json").write_text(json.dumps(ans,indent=1),encoding="utf-8");print(ans)


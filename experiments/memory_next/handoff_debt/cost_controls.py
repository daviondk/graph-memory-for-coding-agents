"""Pairwise cost checks including the inexpensive constant summary and structured note."""
import json
from statistics import mean,median
from score import ROOT,readrows,result
def run():
    rows=readrows("heldout_predictions.csv");obs={r["run_id"]:r for r in readrows("heldout_outcomes.csv")}
    def token(r,v):
        k=r[v] if v in ("stage16","lead20") else v
        return result(obs[r[k]],"prompt_tokens")
    costs={}
    for p in ("raw_trace","structured_notes","summary_notes","repo_only","stage16","lead20"):
        vals=[token(r,p) for r in rows];vals=[v for v in vals if v is not None]
        costs[p]={"n":len(vals),"mean":mean(vals),"median":median(vals),"vs":{}}
        if p in ("stage16","lead20"):
            for base in ("raw_trace","summary_notes","structured_notes"):
                vs=[(token(r,p),token(r,base)) for r in rows]
                ds=[(a-b,b) for a,b in vs if a is not None and b is not None]
                costs[p]["vs"][base]={"n":len(ds),"mean_delta":mean(d for d,b in ds),
                                    "relative":sum(d for d,b in ds)/sum(b for d,b in ds)}
    return costs
if __name__=="__main__":
    (ROOT/"heldout_cost_controls.json").write_text(json.dumps(run(),indent=1),encoding="utf-8")


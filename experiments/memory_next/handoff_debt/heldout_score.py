"""Offline held-out metrics; no pyarrow, network or source-run texts needed."""
from collections import Counter
import json
from statistics import mean
from score import ROOT,VIEWS,readrows,result,contrasts

POLICIES=["receiver","stage16","lead20","manual"]
def compute():
    predictions=readrows("heldout_predictions.csv")
    obs={r["run_id"]:r for r in readrows("heldout_outcomes.csv")}
    assert len(predictions)==80 and len(obs)==320
    fit=json.loads((ROOT/"fit.json").read_text(encoding="utf-8"))
    assert set(fit["train_ids"]).isdisjoint(fit["test_ids"])
    ds=[]
    for r in predictions:
        q={k:r[k] for k in ["instance","pred","succ","stage","checkpoint","attempt"]}
        q.update({v:obs[r[v]] for v in VIEWS[:-1]})
        for v in POLICIES:q[v]=q[r[v]]
        ds.append(q)
    all_results={}
    for kind,rows in [("all",ds)]+[(a,[r for r in ds if r["attempt"]==a]) for a in ("r02","r03")]+[(s,[r for r in ds if r["stage"]==s]) for s in sorted({r["stage"] for r in ds})]:
        out={}
        for arm in [*VIEWS[:-1],*POLICIES]:
            out[arm]={"hits":sum(result(r[arm],"success") for r in rows),"known":sum(r[arm]["official_known"]=="1" for r in rows),"n":len(rows)}
        pairs={}
        for a,b in [("stage16","receiver"),("lead20","raw_trace"),("lead20","receiver"),("manual","structured_notes"),("stage16","raw_trace")]:
            rr=[{**r,"policy":r[a]} for r in rows];pairs[a+"_vs_"+b]=contrasts(rr,bs=(kind=="all"),other=b)
            if kind=="all":pairs[a+"_vs_"+b+"_known"]=contrasts(rr,layer="known",bs=True,other=b)
        all_results[kind]={"arms":out,"pairs":pairs}
    return {"train_tasks":len(fit["train_ids"]),"test_tasks":len(fit["test_ids"]),
            "assigned":{a:dict(Counter(r[a] for r in predictions)) for a in POLICIES},"groups":all_results}
if __name__=="__main__":
    x=compute()
    (ROOT/"heldout_results.json").write_text(json.dumps(x,indent=1),encoding="utf-8")
    print(x["groups"]["all"]["arms"])
    for k in ("stage16_vs_receiver","lead20_vs_raw_trace","lead20_vs_receiver"):
        d=x["groups"]["all"]["pairs"][k];print(k,{n:d[n] for n in ["n","wins","losses","delta_pp","ci95_pp","p_descriptive","prompt_tokens"]})
    print(x["assigned"])


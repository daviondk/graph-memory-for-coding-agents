"""Freeze same-pool controls with exactly matched explicit visibility masks."""
from panel import *
sys.path.insert(0,str(ROOT.parent/"repo_crossfit"))
from fit_crossfit import extract,certify,union_value,utility,rank,order,dev_scores,best,GRID
import numpy as np
from data import labels,get
from supervision import estimate


def main():
    records=read(R34/"features.json.gz")
    fields=extract(records)
    choice=read(R34/"selection.json")["modes"]["union_cost"]
    base=read(R34/"models.json")[choice]
    tr={q for q,r in records.items() if r["split"]=="train"}
    dev={q for q,r in records.items() if r["split"]=="dev"}
    panel=set(read(ROOT/"panel.json")["states"])
    y=labels(tr|dev)
    dr=certify(records,{q:y[q] for q in dev})
    assert panel.isdisjoint(y)
    rows={}
    vals={}
    for q,r in records.items():
        u=union_value(r,base)
        x=fields[q]
        x[:,3]=np.log1p(rank(u))
        x[:,4]=u
        rows[q]={"ids":r["ids"],"x":x,"u":u}
        vals[q]=u
    bundle={}
    for q in panel:
        bm=-np.array(records[q]["ranks"]["dense_state"],float)
        observed=rows[q]["x"][:,11]
        ids=rows[q]["ids"]
        bundle[q]={m:[ids[i] for i in order(v)[:8]] for m,v in {
            "bge":bm,"bge_seen":bm-1e5*observed,"union":vals[q],"union_seen":vals[q]-1e5*observed}.items()}
    selections={}
    old=read(R39/"supervision-predictions.json.gz")
    for mode in ("one_distance","one_distance_no_seen"):
        model=estimate(rows,{q:y[q] for q in tr},mode)
        components={}
        for q in dev|panel:
            x=rows[q]["x"].copy()
            if mode.endswith("_no_seen"):
                x[:,11]=0
            components[q]=utility(vals[q]),utility(model.decision_function(x))
        def scores(q,alpha):
            u,v=components[q]
            return (1-alpha)*u+alpha*v
        grid={a:dev_scores(records,dr,{q:order(scores(q,a))[:8] for q in dev}) for a in GRID}
        a=best(grid)
        selections[mode]={"alpha":a,"dev":grid}
        for q in panel:
            ids=rows[q]["ids"]
            score=scores(q,a)
            observed=rows[q]["x"][:,11]
            plain=[ids[i] for i in order(score)[:8]]
            if mode=="one_distance":
                assert plain==old[q]["one_distance"]
                bundle[q]["R39"]=plain
            else:
                bundle[q]["r39_no_observed"]=plain
                bundle[q]["r39_no_observed_seen"]=[ids[i] for i in order(score-1e5*observed)[:8]]
    write("matched-forecasts.json",bundle)
    write("matched-seal.json",dict(forecasts=sha(ROOT/"matched-forecasts.json"),protocol=sha(ROOT/"MATCHED_PROTOCOL_RU.md"),
                                 code=sha(Path(__file__)),panel=sha(ROOT/"panel.json"),selection=selections))
    print("Frozen",len(bundle),"controls in each policy on the prespecified panel.")

if __name__=="__main__":
    main()

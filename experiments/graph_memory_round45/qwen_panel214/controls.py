"""Build full 214-state rankings from the prespecified R39 train/dev and matched masks."""
from common import *
from matched import (extract, certify, union_value, utility, rank, order, dev_scores, best, GRID, labels, estimate, R39)


def main():
    panel=read(OUT/"panel.json")
    qs=set(panel["order"])
    source=read(R34/"features.json.gz")
    fields=extract(source)
    selected=read(R34/"selection.json")["modes"]["union_cost"]
    old_model=read(R34/"models.json")[selected]
    tr={q for q,row in source.items() if row["split"]=="train"}
    dev={q for q,row in source.items() if row["split"]=="dev"}
    assert len(tr)==179 and len(dev)==101 and (tr|dev).isdisjoint(qs)
    y=labels(tr|dev)
    dc=certify(source,{q:y[q] for q in dev})
    rows={};us={}
    for q,r in source.items():
        u=union_value(r,old_model);us[q]=u
        X=fields[q];X[:,3]=np.log1p(rank(u));X[:,4]=u
        rows[q]={"ids":r["ids"],"x":X,"u":u}
    ranks={};obs={}
    for q in qs:
        ids=rows[q]["ids"]
        seen=rows[q]["x"][:,11];obs[q]=int(seen.sum())
        dense=-np.array(source[q]["ranks"]["dense_state"],float)
        ranks[q]={name:[ids[i] for i in order(v)[:8]] for name,v in {
            "bge":dense,"bge_seen":dense-1e5*seen,"union":us[q],"union_seen":us[q]-1e5*seen}.items()}
    selection={};initial=read(R39/"supervision-predictions.json.gz")
    for mode in ("one_distance","one_distance_no_seen"):
        model=estimate(rows,{q:y[q] for q in tr},mode)
        cs={}
        for q in dev|qs:
            xx=rows[q]["x"].copy()
            if mode.endswith("_no_seen"):xx[:,11]=0
            cs[q]=(utility(us[q]),utility(model.decision_function(xx)))
        def score(q,a):
            x,v=cs[q]
            return (1-a)*x+a*v
        grid={a:dev_scores(source,dc,{q:order(score(q,a))[:8] for q in dev}) for a in GRID}
        a=best(grid);selection[mode]=dict(alpha=a,dev=grid)
        for q in qs:
            ids=rows[q]["ids"];seen=rows[q]["x"][:,11];v=score(q,a)
            top=[ids[i] for i in order(v)[:8]]
            if mode=="one_distance":
                assert top==initial[q]["one_distance"]
                ranks[q]["R39"]=top
            else:
                ranks[q]["r39_no_observed"]=top
                ranks[q]["r39_no_observed_seen"]=[ids[i] for i in order(v-1e5*seen)[:8]]
    pilot=read(R39SRC/"matched-forecasts.json")
    assert all(ranks[q]==p for q,p in pilot.items())
    seal=read(R39SRC/"matched-seal.json")
    assert json.loads(json.dumps(selection))==seal["selection"]
    save("control-ranks.json.gz",ranks)
    save("controls-seal.json",dict(inputs=sha(OUT/"panel.json"),program=sha(Path(__file__)),forecasts=sha(OUT/"control-ranks.json.gz"),
                                 train=len(tr),dev=len(dev),matches_pilot=len(pilot),choice=selection,observed_counts=obs))
    print("Sealed matched controls on 214. Ten R39 pilot rankings and both dev curves reproduced.")


if __name__=="__main__":
    main()

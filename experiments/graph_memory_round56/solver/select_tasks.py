"""Calibrate the published check independently of model answers; freeze all selected material."""
from collections import defaultdict
from study import *
from isolation import execute

def main():
    tasks=read("candidates.json.gz");hist=read("history.json.gz")
    # Process a deterministic initial candidate prefix per project. If a prefix does
    # not contain twelve eligible tasks, extend until the target or list ends.
    pools={repo:sorted((q for q,t in tasks.items() if t["repo"]==repo),key=lambda q:digest(q.encode())) for repo in SPECS}
    eligible={repo:[] for repo in SPECS};at={repo:0 for repo in SPECS};tested={}
    while True:
        batch=[]
        for repo in SPECS:
            if len(eligible[repo])>=12:continue
            start=at[repo];end=min(start+18,len(pools[repo]))
            for q in pools[repo][start:end]:
                r=tasks[q]
                for k in ("reference","stub"):
                    batch.append(dict(id=q+"|"+k,repo=repo,path=r["path"],name=r["name"],kind=k))
            at[repo]=end
        if not batch:break
        checked=execute(batch);tested.update(checked)
        for repo in SPECS:
            eligible[repo]=[q for q in pools[repo][:at[repo]] if tested[q+"|reference"]["passed"] and not tested[q+"|stub"]["passed"]
                            and tested[q+"|stub"]["run"]==tested[q+"|reference"]["run"]]
    selected={q:tasks[q] for qs in eligible.values() for q in qs[:12]}
    forecasts={}
    for q,t in selected.items():
        h=hist[t["repo"]];es=h["episodes"];scores=score_query(es,t)
        local=sorted({e["i"] for e in es if t["path"] in e["anchors"]})
        pool={"file8":set(local[-8:]),"file_all":set(local),
              "global32":set(range(len(h["commits"])-32,len(h["commits"]))),"full_bm25":set(range(len(h["commits"])))}
        arms={}
        for arm,avail in pool.items():
            indices=[i for i,e in enumerate(es) if e["i"] in avail]
            default=not indices
            if default:indices=list(range(len(es)))
            # A duplicate text has identical BM25 except when address tokens differ.
            # Keep its highest scoring instance, resolving equal scores by age.
            def order(i):return -scores[i],-es[i]["i"],es[i]["path"],es[i]["address"]
            top=min(indices,key=order);e=es[top]
            arms[arm]=dict(id=top,sha=e["sha"],selection_score=scores[top],
                           seen_unique_texts=len({es[i]["text"] for i in indices}),fallback=default,
                           name=e["address"],path=e["path"],text=e["text"])
        forecasts[q]=dict(task=t,evidence=arms,anchor_transactions=len(local))
    write("calibration.json.gz",tested);write("selections.json.gz",forecasts)
    write("selection-seal.json",dict(considered={r:at[r] for r in SPECS},eligible={r:len(v) for r,v in eligible.items()},
            selected=len(selected),hashes={n:digest((HERE/n).read_bytes()) for n in
                ("PROTOCOL_RU.md","study.py","prepare.py","isolation.py","select_tasks.py","pins.json","history.json.gz","candidates.json.gz","calibration.json.gz","selections.json.gz")}))
    print("selected",len(selected),{r:(len(pools[r]),at[r],len(eligible[r])) for r in SPECS},flush=True)
    print("rows with changed evidence",sum(len({a["text"] for a in row["evidence"].values()})>1 for row in forecasts.values()))
if __name__=="__main__":
    main()

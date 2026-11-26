"""Join two sealed forecast files to native judgments only after the complete GPU run."""
from common import *
sys.path.insert(0,str(WORK/"graph_memory_round39/repo_crossfit"))
from evaluate import native, labels, score_state

METRICS=["CompleteMSS@5","CompleteMSS@8","CompleteMSS@8_under2048","CompleteMSS@8_under6144","GroupRecall@5","GroupRecall@8","Necessity@5"]
PAIRS=[("r39_no_observed_seen","qwen_seen"),("r39_no_observed","qwen"),("R39","qwen_seen"),
       ("qwen","bge"),("qwen_seen","bge_seen"),("qwen_seen","union_seen"),("qwen_seen","qwen")]


def describe(qs, rows, arms, pairs=PAIRS):
    M=np.array([[rows[q]["arms"][a] for a in arms] for q in qs],float)
    repos, ix=np.unique([rows[q]["repo"] for q in qs], return_inverse=True)
    counts=np.bincount(ix)
    totals=np.zeros((len(counts),len(arms),len(METRICS)),float);np.add.at(totals,ix,M)
    rr=totals/counts[:,None,None]
    results={a:dict(complete_counts=M[:,j,:4].sum(0).astype(int).tolist(),
                    micro=M[:,j].mean(0).tolist(),macro_repo=rr[:,j].mean(0).tolist(),
                    returned_tokens=np.mean([rows[q]["tokens"][a] for q in qs],axis=0).tolist()) for j,a in enumerate(arms)}
    rng=np.random.default_rng(4021406);draw=rng.integers(len(counts),size=(10000,len(counts)))
    W=np.stack([np.bincount(row,minlength=len(counts)) for row in draw])
    div=(W@counts)[:,None]
    comparisons={}
    for a,b in pairs:
        i,j=arms.index(a),arms.index(b);D=M[:,i]-M[:,j];dr=totals[:,i]-totals[:,j];dm=rr[:,i]-rr[:,j]
        comparisons[a+" minus "+b]=dict(delta=D.mean(0).tolist(),
          ci95=np.quantile((W@dr)/div,[.025,.975],axis=0).tolist(),macro=dm.mean(0).tolist(),
          macro95=np.quantile((W@dm)/len(counts),[.025,.975],axis=0).tolist(),wins=(D>1e-10).sum(0).tolist(),losses=(D< -1e-10).sum(0).tolist())
    return dict(states=len(qs),repos=len(counts),methods=results,contrasts=comparisons)


def score_one(row,gold,ranks):
    outcomes=score_state(row,gold,ranks)
    tk=dict(zip(row["ids"],row["qw"]));tokens={}
    # Cache the ideal denominator by depth: it depends on the label, never on a prediction.
    original_ideal=native.ideal_group_dcg;cache={}
    def ideal(groups,weights,k):
        if k not in cache:cache[k]=original_ideal(groups,weights,k)
        return cache[k]
    native.ideal_group_dcg=ideal
    try:
        for method,seq in ranks.items():
            at5=native.score_prediction(seq,gold,5);at8=native.score_prediction(seq,gold,8)
            assert outcomes[method][:2]==[at5["mss_complete@5"],at8["mss_complete@8"]]
            outcomes[method].extend([at5["group_recall@5"],at8["group_recall@8"],at5["necessity_weighted_recall@5"]])
            cc=np.cumsum([tk[i] for i in seq])
            tokens[method]=[int(cc[4]),int(cc[7]),int(sum(tk[i] for j,i in enumerate(seq) if cc[j]<=2048)),
                            int(sum(tk[i] for j,i in enumerate(seq) if cc[j]<=6144))]
    finally:native.ideal_group_dcg=original_ideal
    return outcomes,tokens


def main():
    qs=read(OUT/"panel.json");seal=read(OUT/"gpu-seal.json");control=read(OUT/"controls-seal.json")
    assert sha(OUT/"qwen-scores.json.gz")==seal["forecasts"] and sha(OUT/"control-ranks.json.gz")==control["forecasts"]
    data=read(OUT/"qwen-scores.json.gz");c=read(OUT/"control-ranks.json.gz");original=read(R34/"features.json.gz")
    assert len(data)==214 and set(data)==set(qs["order"])==set(c)
    source_gold=labels(set(data));per={};forecasts={}
    started=time.perf_counter()
    for q in qs["order"]:
        row=original[q];gold=source_gold[q];rr=data[q]
        assert set(rr["scores"])==set(row["ids"])
        ranks=c[q]|rr["ranks"]; forecasts[q]=ranks
        outcomes,tokens=score_one(row,gold,ranks)
        per[q]={"repo":row["repo"],"arms":outcomes,"tokens":tokens,"seen":control["observed_counts"][q]}
    prior=read(R39SRC/"reference-outcomes.json")
    for q,o in prior.items():
        for name,arr in o["metrics"].items():
            if seal["matched_pilot"][q]["sameLists"] or name not in ("qwen","qwen_seen"):
                assert per[q]["arms"][name][:4]==arr
    arms=sorted(next(iter(per.values()))["arms"])
    panels={}
    for name,ids in (("all214",qs["order"]),("outside204",qs["remaining"]),("pilot10",qs["pilot"])):
        panels[name]=describe(ids,per,arms)
        if name!="pilot10":
            for overlap in (False,True):
                subset=[q for q in ids if bool(per[q]["seen"])==overlap]
                panels[name+("_overlap" if overlap else "_no_overlap")]=describe(subset,per,arms)
    resources={}
    for name,ids in (("all214",qs["order"]),("outside204",qs["remaining"]),("pilot10",qs["pilot"])):
        records=[data[q] for q in ids]
        resources[name]=dict(states=len(ids),candidates=sum(len(r["scores"]) for r in records),
                             strings=sum(len(r["lengths"]) for r in records),truncated=sum(r["truncated"] for r in records),
                             seconds=sum(r["seconds"] for r in records),tokens=sum(r["tokens"] for r in records))
    save("predictions.json.gz",forecasts);save("outcomes.json.gz",per)
    save("results.json",dict(metrics=METRICS,panels=panels,resources=resources,grading_seconds=time.perf_counter()-started,
                             gpu_seal=sha(OUT/"gpu-seal.json"),controls=sha(OUT/"controls-seal.json"),outcomes=sha(OUT/"outcomes.json.gz")))
    for name in ("all214","outside204","pilot10"):
        print(name,{a:r["complete_counts"] for a,r in panels[name]["methods"].items()})


if __name__=="__main__":
    main()

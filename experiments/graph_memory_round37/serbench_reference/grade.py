"""Official Complete-MSS on frozen predictions for the same 214 states."""
from pathlib import Path
from common import D, R34, PUB, data, get, native, np, rows, save, sha
METRICS=("at5","at8","at8_2048Qwen","at8_6144Qwen","at8_2048WP")
def main():
    frozen=get(D/"seal.json");assert all(sha(D/p)==s for p,s in frozen["files"].items())
    predictions=get(D/"predictions.json.gz");features=data()
    labels={r["state_id"]:r for r in rows(PUB/"labels.jsonl.gz") if r["state_id"] in predictions}
    assert labels.keys()==predictions.keys()
    old=get(R34/"strong/test-outcomes.json.gz"); states={}
    for sid,methods in predictions.items():
        f=features[sid];qwen=dict(zip(f["ids"],f["qw"]));wp=dict(zip(f["ids"],f["wp"]));label=labels[sid]
        orig=native.ideal_group_dcg; memo={}
        def cached(gs,w,k):
            if k not in memo:memo[k]=orig(gs,w,k)
            return memo[k]
        native.ideal_group_dcg=cached
        try:
            vals={};cost_bins={}
            for name,ids in methods.items():
                assert len(ids)==len(set(ids))==8 and set(ids)<=qwen.keys()
                def score(kept,k):return int(native.score_prediction(kept,label,k)[f"mss_complete@{k}"])
                metrics=[score(ids,5),score(ids,8)];cuts=[]
                for costs,budget in ((qwen,2048),(qwen,6144),(wp,2048)):
                    length=int((np.cumsum([costs[i] for i in ids])<=budget).sum())
                    metrics.append(score(ids[:length],8));cuts.append(length)
                if name in ("dense_state","union_cost","bm25"):
                    prev=old[sid]["arms"][name]
                    assert [metrics[i] for i in (0,1,3,4)]==[prev[i] for i in (1,2,0,4)]
                vals[name]=metrics;cost_bins[name]=cuts
        finally:native.ideal_group_dcg=orig
        states[sid]=dict(repo=f["repo"],scores=vals,cuts=cost_bins)
    save(D/"outcomes.json.gz",states)
    ids=sorted(states);methods=sorted(states[ids[0]]["scores"])
    vals={m:np.array([states[q]["scores"][m] for q in ids]) for m in methods}
    reps=sorted({x["repo"] for x in states.values()});indices=[[i for i,q in enumerate(ids) if states[q]["repo"]==r] for r in reps]
    n=len(reps);size=np.array([len(i) for i in indices]);sample=np.random.default_rng(370624).integers(n,size=(20000,n))
    draws=np.zeros((len(sample),n),int);np.add.at(draws,(np.arange(len(sample))[:,None],sample),1)
    result={}
    for m in ("mmr","cross_encoder"):
        for b in ("dense_state","union_cost"):
            d=vals[m]-vals[b];cluster=np.stack([d[i].sum(0) for i in indices])
            boot=draws@cluster/(draws@size)[:,None]
            result[m+" minus "+b]=dict(delta=d.mean(0).tolist(),ci95=np.quantile(boot,[.025,.975],axis=0).tolist(),
                won=(d>0).sum(0).tolist(),lost=(d<0).sum(0).tolist())
    res=dict(states=len(ids),repos=n,metrics=METRICS,successes={m:v.sum(0).tolist() for m,v in vals.items()},comparisons=result,
             states_with_cap={m:(np.array([states[q]["cuts"][m] for q in ids])<8).sum(0).tolist() for m in methods},
             official_checks=len(ids)*len(methods)*len(METRICS),old_outcome_matches=len(ids)*3*4,
             labels=sha(PUB/"labels.jsonl.gz"),scorer=sha(Path(native.__file__)))
    save(D/"results.json",res);print(res["successes"])
    for c,x in result.items():print(c,[round(v*100,2) for v in x["delta"]],[[round(v*100,2) for v in j] for j in x["ci95"]],x["won"],x["lost"])
if __name__=="__main__":main()

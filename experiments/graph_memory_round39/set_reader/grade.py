"""Score sealed predictions with SERBench and estimate paired repository-level uncertainty."""
from data import *
METRICS=("CompleteMSS@5","CompleteMSS@8","MSS@8_2048Qwen","MSS@8_6144Qwen","GroupRecall@8")
def main():
    seal=get(D/"seal.json")
    assert sha(D/"predictions.json.gz")==seal["predictions"] and sha(D/"selection.json")==seal["selection"]
    predictions=get(D/"predictions.json.gz")
    data=get(STRONG/"features.json.gz");truth=labels(set(predictions));out={}
    old=get(R37/"outcomes.json.gz");checks=0
    for q,arms in predictions.items():
        r=data[q];label=truth[q];cost=dict(zip(r["ids"],r["qw"]));route=sets_native(r["ids"],label)
        original=native.ideal_group_dcg;cache={}
        def ideal(groups,weights,k):
            if k not in cache:cache[k]=original(groups,weights,k)
            return cache[k]
        native.ideal_group_dcg=ideal
        try:
            memo={};values={}
            for name,ret in arms.items():
                assert len(ret)==8 and len(set(ret))==8
                def native_scores(seq,k):
                    key=(tuple(seq),k)
                    if key not in memo:memo[key]=native.score_prediction(seq,label,k)
                    return memo[key]
                cum=np.cumsum([cost[x] for x in ret]);d=native_scores(ret,8)
                vals=[native_scores(ret,5)["mss_complete@5"],d["mss_complete@8"]]
                selected=[ret[:5],ret[:8]]
                for budget in (2048,6144):
                    available=ret[:int(np.sum(cum<=budget))]
                    vals.append(native_scores(available,8)["mss_complete@8"]);selected.append(available)
                vals.append(d["group_recall@8"])
                for k,sub in enumerate(selected):
                    inds=frozenset(r["ids"].index(i) for i in sub)
                    assert vals[k]==int(any(a<=inds for a in route)),(q,name,k,vals[k])
                if name in old[q]["scores"]:assert vals[:4]==old[q]["scores"][name][:4]
                values[name]=vals;checks+=4
            out[q]=dict(repo=r["repo"],task=r["task"],arms=values)
        finally:native.ideal_group_dcg=original
    save("outcomes.json.gz",out)
    qs=sorted(out);names=sorted(out[qs[0]]["arms"]);matrix=np.array([[out[q]["arms"][a] for a in names] for q in qs])
    repos,idx=np.unique([out[q]["repo"] for q in qs],return_inverse=True);n=len(repos)
    counts=np.bincount(idx);rng=np.random.default_rng(39013)
    bs=rng.integers(n,size=(10000,n));weights=np.stack([np.bincount(x,minlength=n) for x in bs]);div=(weights@counts)[:,None]
    contrasts={}
    pairs=[("conditional",b) for b in names if b!="conditional"]+[("matched_unary","union_cost"),("forced","matched_unary"),("frozen_joint","union_cost"),("union_unseen","union_cost")]
    for a,b in pairs:
        diff=matrix[:,names.index(a)]-matrix[:,names.index(b)];agg=np.zeros((n,len(METRICS)));np.add.at(agg,idx,diff)
        draws=(weights@agg)/div
        contrasts[a+" minus "+b]=dict(delta=diff.mean(0).tolist(),ci95=np.quantile(draws,[.025,.975],axis=0).tolist(),
                                      wins=(diff>1e-12).sum(0).tolist(),losses=(diff< -1e-12).sum(0).tolist(),
                                      different_top5_order=sum(predictions[q][a][:5]!=predictions[q][b][:5] for q in qs),
                                      different_top5_set=sum(set(predictions[q][a][:5])!=set(predictions[q][b][:5]) for q in qs))
    stats={a:dict(successes=matrix[:,i,:4].sum(0).astype(int).tolist(),mean=matrix[:,i].mean(0).tolist()) for i,a in enumerate(names)}
    result=dict(metrics=METRICS,states=len(qs),repos=n,bootstrap=10000,arms=stats,contrasts=contrasts,complete_route_checks=checks,
                native=sha(Path(native.__file__)),seal=sha(D/"seal.json"),outcomes=sha(D/"outcomes.json.gz"))
    save("results.json",result)
    print({a:v["successes"] for a,v in stats.items()});print({a:contrasts["conditional minus "+a] for a in ("union_cost","matched_unary","shuffled")})
if __name__=="__main__":main()


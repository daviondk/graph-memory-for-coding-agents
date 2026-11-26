"""Post hoc factorial attribution. Fit on train and select each fusion coefficient only on dev."""
from fit import *
def estimate(data,gold,mode):
    many=mode.startswith("many")
    marginal="distance" in mode
    blocks=[];ys=[];ws=[]
    for q in sorted(gold):
        r=data[q];routes=sets_native(r["ids"],gold[q]);n=len(r["ids"])
        if not routes:continue
        allpos=set().union(*routes)
        prefix=contexts(q,r,routes) if many else [()]
        samples=[]
        for s in prefix:
            original=target(routes,s,n)
            if original is None:continue
            ix=np.array([i for i in range(n) if i not in s])
            yy=original[ix] if marginal else np.array([i in allpos for i in ix])
            if not yy.any() or yy.all():continue
            w=np.where(yy,.5/yy.sum(),.5/(~yy).sum())
            x=r["x"][ix].copy()
            if mode.endswith("_no_seen"):x[:,11]=0
            samples.append((x,yy,w))
        for x,y,w in samples:
            blocks.append(x);ys.append(y);ws.append(w/len(samples))
    X=np.vstack(blocks);Y=np.concatenate(ys);weight=np.concatenate(ws);weight*=len(X)/weight.sum()
    model=HistGradientBoostingClassifier(max_iter=65,learning_rate=.09,max_leaf_nodes=7,min_samples_leaf=55,
        l2_regularization=4,early_stopping=False,random_state=39013).fit(X,Y,sample_weight=weight)
    return model
def freeze():
    data=inference();train={q for q,r in data.items() if r["split"]=="train"};dev={q for q,r in data.items() if r["split"]=="dev"}
    g=labels(train|dev);out={q:{} for q,r in data.items() if r["split"]=="test"};frozen={}
    for mode in ("one_union","one_distance","many_union","many_distance","many_distance_no_seen"):
        model=estimate(data,{q:g[q] for q in train},mode)
        linear={}
        for q,r in data.items():
            if q in train:continue
            x=r["x"].copy()
            if mode.endswith("_no_seen"):x[:,11]=0
            linear[q]=(util(r["u"]),util(model.decision_function(x)))
        scores={z:sum((simple(data[q],order(mix(*linear[q],z))[:8],g[q]) for q in sorted(dev)),np.zeros(3,dtype=int)) for z in GRID}
        pick=choose(scores);frozen[mode]=dict(alpha=pick,dev={k:v.tolist() for k,v in scores.items()})
        for q in out:out[q][mode]=[data[q]["ids"][i] for i in order(mix(*linear[q],pick))[:8]]
    old=get(D/"predictions.json.gz")
    assert all(out[q]["many_distance"]==old[q]["matched_unary"] for q in out)
    save("supervision-predictions.json.gz",out)
    save("supervision-seal.json",dict(dev=frozen,forecasts=sha(D/"supervision-predictions.json.gz"),protocol=sha(D/"SUPERVISION_RU.md"),code=sha(Path(__file__))))
def grade():
    from scipy import stats
    rows=get(D/"supervision-predictions.json.gz");assert sha(D/"supervision-predictions.json.gz")==get(D/"supervision-seal.json")["forecasts"]
    data=get(STRONG/"features.json.gz");g=labels(set(rows));old=get(D/"outcomes.json.gz")
    qs=sorted(rows);modes=sorted(rows[qs[0]])
    arr=np.zeros((len(qs),len(modes),4),int)
    for j,q in enumerate(qs):
        r=data[q];ids=r["ids"];cost=dict(zip(ids,r["qw"]));routes=sets_native(ids,g[q])
        for k,m in enumerate(modes):
            rank=rows[q][m];cum=np.cumsum([cost[i] for i in rank])
            ks=[5,8,int((cum<=2048).sum()),int((cum<=6144).sum())]
            for z,depth in enumerate(ks):
                ss={ids.index(i) for i in rank[:depth]};arr[j,k,z]=any(a<=ss for a in routes)
        assert np.array_equal(arr[j,modes.index("many_distance")],old[q]["arms"]["matched_unary"][:4])
    repos,idx=np.unique([data[q]["repo"] for q in qs],return_inverse=True);cnt=np.bincount(idx)
    rng=np.random.default_rng(39131);draw=rng.integers(len(cnt),size=(10000,len(cnt)))
    N=np.stack([np.bincount(s,minlength=len(cnt)) for s in draw]);division=(N@cnt)[:,None]
    pairs=[("many_distance","many_union"),("many_distance","one_distance"),("many_union","one_union"),("one_distance","one_union"),("many_distance","many_distance_no_seen")]
    contrast={}
    for a,b in pairs:
        diff=arr[:,modes.index(a)]-arr[:,modes.index(b)];agg=np.zeros((len(cnt),4));np.add.at(agg,idx,diff)
        contrast[a+" minus "+b]=dict(delta=diff.mean(0).tolist(),ci95=np.quantile((N@agg)/division,[.025,.975],axis=0).tolist(),
                                     wins=(diff>0).sum(0).tolist(),losses=(diff<0).sum(0).tolist())
    result=dict(successes={m:arr[:,j].sum(0).tolist() for j,m in enumerate(modes)},matched=214,contrasts=contrast,seal=sha(D/"supervision-seal.json"))
    save("supervision-results.json",result)
    print(result["successes"])
if __name__=="__main__":
    if sys.argv[1]=="fit":freeze()
    else:grade()


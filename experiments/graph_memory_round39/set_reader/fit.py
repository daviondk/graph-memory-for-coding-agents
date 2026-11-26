"""Fit conditional next-evidence value, choose weights on dev and freeze all test ID lists."""
from data import *
from sklearn.ensemble import HistGradientBoostingClassifier
import sklearn
GRID=(0.,.25,.5,.75,1.)
def contexts(q,r,routes):
    u=order(r["u"]);dense=r["bge"];n=len(u)
    one=sorted(min(routes,key=lambda a:stable(q+"|"+str(sorted(a)))),key=lambda i:stable(q+str(i)))
    allpos=set().union(*routes)
    wrong=[int(i) for i in u if i not in allpos]
    mixed=[v for pair in itertools.zip_longest(one,wrong) for v in pair if v is not None]
    out=set()
    for seq in (u,dense,mixed):
        for k in (0,1,2,4,6):out.add(tuple(sorted(map(int,seq[:k]))))
    return sorted(out,key=lambda s:(len(s),s))
def fit(data,gold):
    blocks=[];ys=[];ws=[];stat=Counter()
    for q in sorted(gold):
        r=data[q];routes=sets_native(r["ids"],gold[q]);n=len(r["ids"])
        if not routes:continue
        parts=[]
        for selected in contexts(q,r,routes):
            yy=target(routes,selected,n)
            if yy is None:continue
            ix=np.array([i for i in range(n) if i not in selected]);lab=yy[ix]
            if not lab.any() or lab.all():continue
            feats=np.column_stack((r["x"],pool(r,selected)))[ix]
            weights=np.where(lab,.5/lab.sum(),.5/(~lab).sum())
            parts.append((feats,lab,weights))
        if not parts:continue
        for xx,y,w in parts:
            blocks.append(xx);ys.append(y);ws.append(w/len(parts))
        stat["states"]+=1;stat["prefixes"]+=len(parts);stat["certificates"]+=len(routes)
    sizes=[len(a) for a in ys]
    X=np.vstack(blocks);Y=np.concatenate(ys);weight=np.concatenate(ws);weight*=len(X)/weight.sum()
    dims=len(next(iter(data.values()))["x"][0]);stat["rows"]=len(X);stat["positive_rows"]=int(Y.sum())
    models=[];exports=[]
    for width in (dims,dims+13):
        model=HistGradientBoostingClassifier(max_iter=65,learning_rate=.09,max_leaf_nodes=7,max_depth=None,min_samples_leaf=55,
                     l2_regularization=4,early_stopping=False,random_state=39013).fit(X[:,:width],Y,sample_weight=weight)
        trees=[]
        for predictors in model._predictors:
            tree=predictors[0].nodes
            trees.append({k:tree[k].tolist() for k in ("value","is_leaf","feature_idx","num_threshold","missing_go_to_left","left","right")})
        exports.append(dict(base=float(model._baseline_prediction.item()),trees=trees,width=width))
        models.append(model)
    save("trees.json.gz",dict(models=exports,training=dict(stat),sklearn=sklearn.__version__))
    return models,dict(stat)
def util(scores):
    return -np.log(rank(scores))
def state_context(r,models):
    z=np.column_stack((r["x"],pool(r,[])))
    return {"u":util(r["u"]),"learned":util(models[0].decision_function(r["x"])),
            "empty":util(models[1].decision_function(z))}
def mix(a,b,alpha):return (1-alpha)*a+alpha*b
def ranked(r,ctx,models,unary,alpha,perm=None):
    if alpha==0:return order(unary)[:8].tolist()
    chosen=[]
    for k in range(8):
        if k:
            joint=util(models[1].decision_function(np.column_stack((r["x"],pool(r,chosen,perm)))))
            score=unary+alpha*(joint-ctx["empty"])
        else:score=unary.copy()
        score[chosen]=-np.inf
        chosen.append(int(np.argmax(score)))
    return chosen
def permutation(q,r):
    rng=np.random.default_rng(int.from_bytes(stable(q+"|set-null")[:8],"big"));result=np.arange(len(r["ids"]))
    ordered=r["bge"]
    for chunk in np.array_split(ordered, min(10,len(ordered))):
        result[chunk]=rng.permutation(chunk)
    return result
def simple(r,indexes,label):
    selected=[r["ids"][i] for i in indexes]
    def complete(k,ls):
        s=set(ls[:k]);return int(all(sum(i in s for i in g["acceptable_evidence_ids"])>=g["minimum_required"] for g in label["required_evidence_groups"]) or any(set(a)<=s for a in label["alternative_minimal_sets"]))
    count=int(np.sum(np.cumsum(r["qw"][indexes])<=2048))
    return np.array([complete(5,selected),complete(8,selected),complete(8,selected[:count])])
def choose(candidates):return max(candidates,key=lambda k:(*candidates[k].tolist(),-k))
def main():
    data=inference();train={q for q,x in data.items() if x["split"]=="train"};dev={q for q,x in data.items() if x["split"]=="dev"}
    labeled=labels(train|dev);models,stat=fit(data,{q:labeled[q] for q in train})
    contexts={q:state_context(r,models) for q,r in data.items() if q not in train}
    values={a:np.zeros(3,dtype=int) for a in GRID};emptyvalues={a:np.zeros(3,dtype=int) for a in GRID}
    for q in sorted(dev):
        r=data[q];ctx=contexts[q]
        for a in GRID:
            values[a]+=simple(r,order(mix(ctx["u"],ctx["learned"],a))[:8],labeled[q])
            emptyvalues[a]+=simple(r,order(mix(ctx["u"],ctx["empty"],a))[:8],labeled[q])
    alpha=choose(values);ealpha=choose(emptyvalues)
    conditional={a:np.zeros(3,dtype=int) for a in GRID}
    for q in sorted(dev):
        r=data[q];ctx=contexts[q];base=mix(ctx["u"],ctx["learned"],alpha)
        for a in GRID:conditional[a]+=simple(r,ranked(r,ctx,models,base,a),labeled[q])
    gamma=choose(conditional)
    sel=dict(unary_weight=alpha,joint_correction=gamma,empty_weight=ealpha,
             dev_unary={str(k):v.tolist() for k,v in values.items()},dev_joint={str(k):v.tolist() for k,v in conditional.items()},
             dev_empty={str(k):v.tolist() for k,v in emptyvalues.items()},training=stat,
             protocol=sha(D/"PROTOCOL_RU.md"),data_program=sha(D/"data.py"),fit=sha(Path(__file__)),trees=sha(D/"trees.json.gz"))
    save("selection.json",sel)
    old=get(R37/"predictions.json.gz");out={}
    for q,r in data.items():
        if r["split"]!="test":continue
        ctx=contexts[q];base=mix(ctx["u"],ctx["learned"],alpha)
        methods={"conditional":ranked(r,ctx,models,base,gamma),"forced":ranked(r,ctx,models,base,1.),
                 "shuffled":ranked(r,ctx,models,base,gamma,permutation(q,r)),
                 "matched_unary":order(base)[:8],"frozen_joint":order(mix(ctx["u"],ctx["empty"],ealpha))[:8],
                 "union_unseen":order(ctx["u"]-1e5*r["seen"])[:8]}
        out[q]={m:[r["ids"][j] for j in ix] for m,ix in methods.items()}|old[q]
        assert out[q]["union_cost"]==[r["ids"][j] for j in order(r["u"])[:8]]
    assert len(out)==214
    save("predictions.json.gz",out)
    save("seal.json",dict(predictions=sha(D/"predictions.json.gz"),selection=sha(D/"selection.json"),inputs=sha(STRONG/"features.json.gz"),
                                previous=sha(R37/"predictions.json.gz"),vectors=sha(UP/"dense_vectors.npy"),items=sha(PUB/"items.jsonl.gz")))
    print(sel,flush=True)
if __name__=="__main__":main()


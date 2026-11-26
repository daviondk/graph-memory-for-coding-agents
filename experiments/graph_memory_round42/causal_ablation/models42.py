"""Matched supervised models and portable representations."""
import os
import hashlib
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[key]="1"
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
from core42 import D,read,save,sha

VARIANTS=("semantic","role_cost","shape","rich","local","cross","full","sham")


def inputs(sem,meta,edge,sham,arm):
    base=[sem]
    if arm=="semantic": return sem
    if arm=="role_cost": return np.column_stack([sem,meta[:,:2]])
    if arm=="shape": return np.column_stack([sem,meta[:,:7]])
    base.append(meta)
    if arm=="sham":base.append(sham)
    elif arm=="full":base.append(edge)
    elif arm=="local":base.extend((edge[:,:4],edge[:,8:12]))
    elif arm=="cross":base.extend((edge[:,4:8],edge[:,12:16]))
    else:assert arm=="rich"
    return np.column_stack(base)


def portable(m,x):
    if "coef" in m:return x@np.asarray(m["coef"])+m["bias"]
    out=np.full(len(x),m["bias"],dtype=float)
    for tree in m["trees"]:
        def visit(j,rows):
            col,split,a,b,value=tree[j]
            if a==b:
                out[rows]+=value
            else:
                passed=x[rows,col]<=split
                if passed.any():visit(a,rows[passed])
                if not passed.all():visit(b,rows[~passed])
        visit(0,np.arange(len(x)))
    return out


def prepare():
    arr={k:[] for k in ("meta","edge","sham","sem13","labels")}
    all_q=0;seen=set();eligible=0;pos=0;neg=0;n_no_pos=n_no_neg=0;covered_t=set();weights=[];null_y=[];null_w=[]
    for i in range(8):
        receipts=read(D/f"features-{i}-seal.json")["rows"]["train"]
        fp=D/f"train-{i}.npz";origin=D/f"train-{i}.json.gz"
        assert [sha(origin),sha(fp)]==receipts
        with np.load(fp) as a:
            y=a["labels"].astype(bool)
            chosen=np.zeros(len(y),dtype=bool);offset=0
            for q,t,n,ids in read(origin):
                assert q not in seen;seen.add(q)
                sl=slice(offset,offset+n);offset+=n
                yy=y[sl];np_=int(yy.sum());nn=n-np_
                all_q+=1
                if np_==0:n_no_pos+=1;continue
                if nn==0:n_no_neg+=1;continue
                chosen[sl]=True;eligible+=1;covered_t.add(t)
                weights.append(np.where(yy,0.5/np_,0.5/nn))
                ix=sorted(range(n),key=lambda i:hashlib.sha256(f"r42-train-null|{q}|{i}".encode()).digest())
                shuffled=yy.copy()
                shuffled[ix]=yy[np.roll(ix,max(1,n//2))]
                assert int(shuffled.sum())==np_
                null_y.append(shuffled)
                null_w.append(np.where(shuffled,0.5/np_,0.5/nn))
                pos+=np_;neg+=nn
            assert offset==len(y)
            for k in arr:arr[k].append(a[k][chosen])
    assert all_q==len(seen)==3894 and n_no_pos+n_no_neg+eligible==all_q
    out={k:np.concatenate(v) for k,v in arr.items()}
    w=np.concatenate(weights)
    assert abs(w.sum()-eligible)<1e-8 and len(w)==pos+neg
    w*=len(w)/w.sum()
    stats=dict(questions=all_q,informative=eligible,informative_trajectories=len(covered_t),no_visible_positive=n_no_pos,
        no_negative=n_no_neg,positive_candidates=pos,negative_candidates=neg)
    fake_y=np.concatenate(null_y);fake_w=np.concatenate(null_w);fake_w*=len(fake_w)/fake_w.sum()
    stats["permuted_label_changes"]=int(np.count_nonzero(out["labels"]!=fake_y))
    return out,w,stats,fake_y,fake_w


def trees_for(x,y,w):
    model=HistGradientBoostingClassifier(max_iter=100,learning_rate=.08,max_leaf_nodes=15,min_samples_leaf=40,
        l2_regularization=1,early_stopping=False,random_state=13).fit(x,y,sample_weight=w)
    trees=[]
    for tree, in model._predictors:
        nodes=[]
        for r in tree.nodes:
            nodes.append([int(r["feature_idx"]),float(r["num_threshold"]),int(r["left"]),int(r["right"]),float(r["value"])])
        trees.append(nodes)
    frozen=dict(bias=float(model._baseline_prediction.item()),trees=trees)
    assert np.max(np.abs(portable(frozen,x[::13])-model.decision_function(x[::13])))<1e-9
    return frozen


def main():
    control=read(D/"supervision-registration.json")
    assert control["protocol"]==sha(D/"SUPERVISION_RU.md")
    a,w,stats,fake_y,fake_w=prepare();y=a["labels"]
    models={}
    for arm in VARIANTS:
        x=inputs(a["sem13"],a["meta"],a["edge"],a["sham"],arm)
        sc=StandardScaler().fit(x,sample_weight=w)
        lr=LogisticRegression(C=1,max_iter=1000,random_state=13).fit(sc.transform(x),y,sample_weight=w)
        assert lr.n_iter_[0]<1000
        co=lr.coef_[0]/sc.scale_
        linear=dict(coef=co.tolist(),bias=float(lr.intercept_[0]-sc.mean_@co))
        assert np.max(np.abs(portable(linear,x[::13])-lr.decision_function(sc.transform(x[::13]))))<1e-9
        models[arm]={"lr":linear,"hgb":trees_for(x,y,w)}
        if arm in ("rich","full"):
            models[arm]["shuffled_labels_hgb"]=trees_for(x,fake_y,fake_w)
        print("fitted",arm,x.shape,flush=True)
    save(D/"models.json",dict(models=models,train=stats,method=sha(D/"METHOD_RU.md"),protocol=sha(D/"registration.json"),
        fit=sha(D/"models42.py"),supervision=sha(D/"supervision-registration.json"),features={str(i):sha(D/f"features-{i}-seal.json") for i in range(8)}))


if __name__=="__main__":
    main()

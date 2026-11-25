"""Train the same fine-grained estimator on the exact CPU graph-training cohorts."""
from pathlib import Path
import sys
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"fine_train"))
import apply as app
from apply import rd,np,save,load,sha,StandardScaler,LogisticRegression,ProcessPoolExecutor
def fit(cohort):
    src=app.G/"cpu_fallback/cohorts.json";selected=set(load(src)[cohort]["t"])
    assert len(selected)==(64 if cohort=="hash64" else 62)
    tag="subset-"+cohort
    with ProcessPoolExecutor(2) as pool:sh=list(pool.map(app.extract,[(i,selected,tag) for i in range(8)]))
    q={k for a in sh for k in a["queries"]};spl=load(app.OLD/"trained_rank/split.json.gz")["train"]
    assert q=={r["q"] for r in spl if r["t"] in selected}
    a=[np.load(app.P/f"{tag}-{i}.npz") for i in range(8)];x=np.vstack([k["x"] for k in a]);y=np.concatenate([k["y"] for k in a]);models={}
    for name,cols in (("full",rd.FULL),("reduced",rd.RED)):
        z=x[:,cols].astype(np.float64);sc=StandardScaler(copy=False).fit(z);sc.transform(z)
        lr=LogisticRegression(C=1,class_weight="balanced",max_iter=2000,random_state=13).fit(z,y)
        models[name]={"columns":cols,"mean":sc.mean_.tolist(),"scale":sc.scale_.tolist(),"coef":lr.coef_[0].tolist(),"offset":float(lr.intercept_[0]),"iters":int(lr.n_iter_[0])}
    save(D/cohort/"model.json",{"questions":len(q),"trajectories":len(selected),"training_rows":len(y),"positive":int(y.sum()),"models":models,"cohort":sha(src),"source":sha(app.G/"vectors-plan.json"),"features":rd.NAMES,"feature_shards":sh,"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"limited.py")})
if __name__=="__main__":
    cohort,action=sys.argv[1:];assert cohort in ("availability","hash64")
    if action=="fit":fit(cohort)
    elif action in ("dense","rgcn_"+cohort):app.predict(action,D/cohort)
    elif action in ("fine_read","fine_lextrain"):app.predict("rgcn_"+cohort,D.parent/action)
    else:raise ValueError(action)

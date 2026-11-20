"""Freeze degree and neighbor-activation ablations before grading the new repositories."""
from experiment import *
from data_io import panel_name,gz
def main():
    write("structure_method_lock.json",{n:sha(D/n) for n in ["STRUCTURE_PROTOCOL_RU.md","structure.py","fit.json","strict_roster.json"]})
    train=[read_cache(p) for p in files("java","train")]
    X=np.vstack([s["f3"] for s,_ in train]);y=[];sw=[]
    for _,m in train:
        for _,repo,n,sz,h,g in m:
            y.extend([i==g for i in range(n)]);sw.extend([1 if i==g else 1/max(1,n-1) for i in range(n)])
    cl={}
    for name,cols in [("degree",list(range(38))),("activation",[*range(38),40,41])]:
        model=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,min_samples_leaf=28,learning_rate=.10,l2_regularization=1,random_state=261119,early_stopping=False)
        cl[name]=(cols,model.fit(X[:,cols],y,sample_weight=sw))
    dest=D/"structure.pred.jsonl.gz"
    with gzip.open(dest,"wt",encoding="utf8") as out:
        for stage,directory in [("public",D/"cache"),("new",D/"strict_cache")]:
            for p in files("java","test"):
                base=directory/p.stem;z=np.load(base.with_suffix(".npz"));meta=json.loads(base.with_suffix(".json").read_bytes())
                scores={key:model.predict_proba(z["f3"][:,cols])[:,1] for key,(cols,model) in cl.items()}
                for row,lo,hi in zip(meta,z["offset"],z["offset"][1:]):
                    panel,i=(panel_name(p.stem),row[0]) if stage=="public" else row[:2]
                    out.write(json.dumps([stage,panel,i,{key:np.argsort(-v[lo:hi],kind="stable").tolist() for key,v in scores.items()}],separators=(",",":"))+"\n")
    write("structure_decision_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"sha256":sha(dest)})
if __name__=="__main__":main()

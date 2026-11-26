from core42 import D,W,CAUSAL,R41,SEEDS,read,sha,save,firstfit
from models42 import inputs,portable,np


def main():
    receipt=read(D/"models.json")
    assert receipt["fit"]==sha(D/"models42.py") and receipt["method"]==sha(D/"METHOD_RU.md")
    models=receipt["models"]
    structur=read(W/"graph_memory_round33/relative_structure/weights.json")["models"]["global_role"]
    shape_coef=np.asarray(structur["coef"])[:7]
    loss=read(W/"graph_memory_round35/calibration_scale/models.json")["models"]["oof_3894"]
    prior={s:(read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"] if s==13 else
        read(W/f"graph_memory_round21/five_seed/seed-{s}/calibration.json")["rank"]) for s in SEEDS}
    seals={};total=0
    for sh in range(8):
        fp=D/f"test-{sh}.npz";rp=D/f"test-{sh}.json.gz"
        assert read(D/f"features-{sh}-seal.json")["rows"]["test"]==[sha(rp),sha(fp)]
        records=read(rp);allrows={}
        with np.load(fp) as a:
            meta,edge,sham=(a[k] for k in ("meta","edge","sham"))
            frozen_shape=meta[:,:7]@shape_coef+structur["intercept"]
            true=np.column_stack([meta[:,:7],edge])@structur["coef"]+structur["intercept"]
            shuffled=np.column_stack([meta[:,:7],sham])@structur["coef"]+structur["intercept"]
            c=np.rint(np.expm1(meta[:,1])).astype(int)
            for s in SEEDS:
                sem=a[f"sem{s}"]
                scores={}
                for arm,package in models.items():
                    x=inputs(sem,meta,edge,sham,arm)
                    for learner,m in package.items():scores[f"{learner}/{arm}"]=portable(m,x)
                z=np.column_stack([sem[:,0],meta[:,1],meta[:,0],meta[:,0]*meta[:,1]])
                correction=(z-loss["center"])/loss["scale"]@loss["weights"]
                rank=np.rint(np.expm1(sem[:,0])).astype(int)
                rx=np.column_stack([-np.log(rank),sem[:,1],sem[:,2]])
                offset=rx@prior[s]["coef"]+prior[s]["intercept"]
                scores["R35"]=true+offset+correction
                scores["R35_zero_degrees"]=frozen_shape+offset+correction
                scores["R35_permuted_degrees"]=shuffled+offset+correction
                src=CAUSAL/f"pred-{s}-{sh}.json.gz"
                assert sha(src)==read(CAUSAL/f"pred-{s}-{sh}-seal.json")["data"]
                previous={q:sets for q,t,pct,pilot,sets in read(src) if pct==50}
                pos=0
                for q,t,n,ids in records:
                    sl=slice(pos,pos+n);pos+=n
                    ext=np.array(ids)
                    cc=c[sl]
                    picked={}
                    for name,score in scores.items():
                        tie=ext if name.startswith("R35") else rank[sl]
                        order=np.lexsort((tie,-score[sl]))
                        picked[name]=ext[firstfit(order,cc)].tolist()
                    assert picked["R35"]==previous[q]["graph_firstfit"],(q,s)
                    dense=ext[firstfit(np.argsort(rank[sl]),cc)].tolist()
                    assert dense==previous[q]["dense_firstfit"]
                    picked["dense"]=dense
                    allrows.setdefault(q,[t,{}])[1][str(s)]=picked
                assert pos==len(c)
        p=D/f"packets-{sh}.json.gz";save(p,allrows);seals[str(sh)]=sha(p);total+=len(allrows)
        print("forecast",sh,len(allrows),flush=True)
    assert total==2000
    save(D/"forecast-seal.json",dict(packets=seals,questions=total,r35_matches=10000,dense_matches=10000,
         models=sha(D/"models.json"),implementation=sha(D/"predict42.py"),registered=sha(D/"registration.json")))


if __name__=="__main__":
    main()

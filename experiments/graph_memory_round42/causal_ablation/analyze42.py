import os
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
from core42 import D,R41,SEEDS,read,save,sha
import numpy as np
import sys
sys.path.insert(0,str(R41))
from analyze import contrasts

COMPARISONS=[
    ("hgb/full","hgb/rich"),
    ("hgb/full","hgb/sham"),("hgb/sham","hgb/rich"),
    ("hgb/full","hgb/local"),("hgb/full","hgb/cross"),
    ("hgb/local","hgb/rich"),("hgb/cross","hgb/rich"),
    ("hgb/rich","hgb/shape"),("hgb/shape","hgb/role_cost"),
    ("hgb/role_cost","hgb/semantic"),("hgb/semantic","dense"),
    ("lr/full","lr/rich"),("lr/full","lr/sham"),
    ("hgb/full","lr/full"),("hgb/rich","lr/rich"),
    ("R35","R35_zero_degrees"),("R35","R35_permuted_degrees"),
    ("R35","native_wo"),("hgb/rich","native_wo"),("hgb/full","native_wo"),
    ("hgb/rich","R35"),("hgb/full","R35"),("hgb/rich","dense"),
    ("lr/rich","dense"),("lr/full","R35"),("hgb/shape","dense"),
    ("hgb/full","shuffled_labels_hgb/full"),("hgb/rich","shuffled_labels_hgb/rich")]


def main():
    p=D/"scores.json.gz";assert read(D/"grade-seal.json")["scores"]==sha(p)
    r=read(p)
    panels={"primary":[v for v in r if v["eligible"] and not v["pilot"]],
            "deferred":[v for v in r if not v["pilot"]],"all":r}
    result={}
    for name,rows in panels.items():
        ts,idx=np.unique([v["t"] for v in rows],return_inverse=True)
        arms=sorted(rows[0]["arms"][str(SEEDS[0])])
        x=np.array([[[v["arms"][str(s)][k] for k in arms] for s in SEEDS] for v in rows])
        means=x.mean(axis=(0,1));each=x.mean(axis=0)
        deltas=np.stack([x[:,:,arms.index(a),:]-x[:,:,arms.index(b),:] for a,b in COMPARISONS],axis=2)
        ci=contrasts(deltas,idx)
        result[name]=dict(n=len(rows),trajectories=len(ts),means={k:means[i].tolist() for i,k in enumerate(arms)},
            seeds={str(s):{k:each[j,i].tolist() for i,k in enumerate(arms)} for j,s in enumerate(SEEDS)},
            paired=[dict(left=a,right=b,mean=deltas[:,:,i,:].mean(axis=(0,1)).tolist(),ci=ci[:,i].tolist(),
                wins=int((deltas[:,:,i,0]>0).sum()),losses=int((deltas[:,:,i,0]<0).sum()))
                    for i,(a,b) in enumerate(COMPARISONS)])
    assert result["primary"]["n"]==901 and result["primary"]["trajectories"]==657
    save(D/"results.json",dict(groups=result,seeds=SEEDS,bootstrap=10000,rng=410141,measures=["FS","coverage","tokens"],
        source=sha(D/"grade-seal.json"),code=sha(D/"analyze42.py")))
    print("primary",result["primary"]["paired"][0],flush=True)


if __name__=="__main__":main()

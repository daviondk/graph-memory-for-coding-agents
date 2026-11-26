import os,sys
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
from io43 import D,R41,SEEDS,ARMS,read,save,sha
sys.path.insert(0,str(R41))
from analyze import contrasts
import numpy as np

PAIRS=[("full","rich"),("full","local"),("full","cross"),("full","sham"),("local","rich"),("cross","rich"),
       ("rich","dense"),("full","dense"),("full","native_wo"),("rich","native_wo"),
       ("R35","native_wo"),("full","R35"),("native_wo","dense")]


def main():
    p=D/"outcomes.json.gz";assert read(D/"scoring.json")["outcomes"]==sha(p);allr=read(p)
    select={"primary":[r for r in allr if r["fired"] and not r["pilot"] and r["eligible"]],
            "fired_eligible":[r for r in allr if r["fired"] and r["eligible"]],
            "nonpilot_fired":[r for r in allr if r["fired"] and not r["pilot"]],
            "fired":[r for r in allr if r["fired"]],
            "nonpilot_assigned":[r for r in allr if not r["pilot"]],"all_assigned":allr}
    out={}
    for name,rows in select.items():
        if not rows:
            out[name]=dict(n=0,trajectories=0);continue
        ts,clusters=np.unique([r["t"] for r in rows],return_inverse=True)
        x=np.array([[[r["arms"][str(s)][arm] if r["fired"] else [0,0,0] for arm in ARMS] for s in SEEDS] for r in rows])
        mu=x.mean(axis=(0,1));sm=x.mean(axis=0)
        delta=np.stack([x[:,:,ARMS.index(a),:]-x[:,:,ARMS.index(b),:] for a,b in PAIRS],axis=2)
        ci=contrasts(delta,clusters)
        out[name]=dict(n=len(rows),trajectories=len(ts),fired=sum(r["fired"] for r in rows),
            eligible=sum(r["eligible"] for r in rows),mean_visible_fraction=np.mean([r["visibility"] for r in rows]),
            means={a:mu[i].tolist() for i,a in enumerate(ARMS)},by_seed={str(s):{a:sm[j,i].tolist() for i,a in enumerate(ARMS)} for j,s in enumerate(SEEDS)},
            paired=[dict(left=a,right=b,mean=delta[:,:,i].mean(axis=(0,1)).tolist(),ci=ci[:,i].tolist(),
                   wins=int((delta[:,:,i,0]>0).sum()),losses=int((delta[:,:,i,0]<0).sum())) for i,(a,b) in enumerate(PAIRS)])
    no=[r for r in allr if not r["fired"]]
    save(D/"results.json",dict(groups=out,nonfired=dict(questions=len(no),trajectories=len({r["t"] for r in no}),
          nonpilot_questions=sum(not r["pilot"] for r in no),nonpilot_trajectories=len({r["t"] for r in no if not r["pilot"]})),
          primary="full minus rich; fired nonpilot visible",measures=["FS","coverage","tokens"],seeds=SEEDS,boot=10000,
          rng=410141,source=sha(D/"scoring.json"),code=sha(D/"analyze43.py")))
    print("primary",out["primary"]["n"],(out["primary"].get("paired") or [None])[0],flush=True)


if __name__=="__main__":main()

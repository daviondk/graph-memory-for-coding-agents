"""Analyze paired support recovery across overlapping questions and optimization seeds."""
import gzip,hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
def main():
    p=ROOT.parent/"isetrace_five_seeds/per-query.json.gz";data=json.loads(gzip.decompress(p.read_bytes()))
    k=data["metrics"].index("full_support_2048");rows=data["rows"]
    questions=sorted({r[1] for r in rows});seeds=sorted({r[0] for r in rows});tr=sorted({r[2] for r in rows})
    idx={q:i for i,q in enumerate(questions)};sc={s:i for i,s in enumerate(seeds)};tc={t:i for i,t in enumerate(tr)}
    x=np.full((len(questions),len(seeds)),99,int);traj=np.full(len(questions),-1)
    for s,q,t,a,b in rows:
        i=idx[q];j=sc[s];assert a[k] in (0,1) and b[k] in (0,1) and x[i,j]==99
        assert traj[i] in (-1,tc[t]);traj[i]=tc[t];x[i,j]=int(b[k]-a[k])
    assert x.shape==(2000,5) and np.isin(x,[-1,0,1]).all()
    wins=(x>0).sum(1);losses=(x<0).sum(1);counts=np.zeros((6,6),int);np.add.at(counts,(wins,losses),1)
    sizes=np.bincount(traj);ts=np.zeros((len(tr),len(seeds)),int);np.add.at(ts,traj,x)
    rng=np.random.default_rng(325000);query_weighted=[];trajectory_weighted=[]
    for _ in range(10000):
        ti=rng.integers(len(tr),size=len(tr));si=rng.integers(5,size=5);v=ts[ti][:,si].mean(axis=1)
        query_weighted.append(100*v.sum()/sizes[ti].sum());trajectory_weighted.append(100*np.mean(v/sizes[ti]))
    public={"n":len(questions),"trajectories":len(tr),"seeds":seeds,"matrix_wins_rows_losses_columns":counts.tolist(),
            "ever_win":int((wins>0).sum()),"ever_loss":int((losses>0).sum()),"both_signs":int(((wins>0)&(losses>0)).sum()),
            "full_ties":int(counts[0,0]),"all_five_win":int(counts[5,0]),"all_five_loss":int(counts[0,5]),
            "delta_pp":100*x.mean(),"trajectory_equal_weight_pp":100*np.mean(ts.mean(axis=1)/sizes),
            "leave_seed_out_pp":[100*np.delete(x,j,axis=1).mean() for j in range(5)],
            "crossed_query_ci":np.quantile(query_weighted,[.025,.975]).tolist(),"crossed_trajectory_ci":np.quantile(trajectory_weighted,[.025,.975]).tolist(),
            "raw":hashlib.sha256(p.read_bytes()).hexdigest()}
    (ROOT/"results.json").write_text(json.dumps(public,indent=2)+"\n",encoding="utf8");print(public)
if __name__=="__main__":main()

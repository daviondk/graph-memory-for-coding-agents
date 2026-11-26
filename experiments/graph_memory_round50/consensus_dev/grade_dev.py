"""Grade only sealed, complete packet selections; blocks are complete source trajectories."""
import gzip,os,sys
from pathlib import Path
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
    os.environ[k]="1"
import numpy as np
D=Path(__file__).resolve().parent
W=D.parents[1];P=D.parent/"packet_consensus"
sys.path.insert(0,str(P))
from grade_packets import analysis,read,put,sha,SEEDS

def main():
    assert sha(D/"packets.json.gz")==read(D/"forecast-seal.json")["forecasts"]
    raw=read(D/"packets.json.gz");pool=read(D/"pool.json.gz")
    g=W/"graph_memory_round34/interval_witness";gold=g/"dev-atoms.json.gz"
    assert sha(gold)==read(g/"dev-geometry.json")["atoms"]
    atoms=read(gold);assert set(atoms)==set(raw)==set(pool)
    put(D/"dev-judgments.json.gz",{q:[[hi-lo,ws] for _,lo,hi,ws in marks] for q,marks in atoms.items()})
    obs={}
    for q,(t,panels) in raw.items():
        spans=atoms[q];total=sum(hi-lo for _,lo,hi,_ in spans);out=[]
        for cp,marks in enumerate(panels):
            by={}
            for a,ids in marks.items():
                sel=set(ids);assert len(sel)==len(ids)
                weight=sum(hi-lo for _,lo,hi,ws in spans if sel.intersection(ws))
                cost=sum(pool[q]["c"][i] for i in ids)
                assert 0<=weight<=total and 0<=cost<=2048
                by[a]=[int(weight==total),weight/total,cost]
            by["mean_single"]=np.mean([by[f"single_{s}"] for s in SEEDS],axis=0).tolist()
            out.append(by)
        obs[q]=[t,out]
    put(D/"outcomes.json.gz",obs);res=analysis(obs);ex={}
    groups=sorted({r[0] for r in obs.values()});ind={t:j for j,t in enumerate(groups)}
    counts=np.array([sum(z[0]==t for z in obs.values()) for t in groups])
    rng=np.random.default_rng(50084)
    samples=np.vstack([rng.multinomial(len(groups),np.full(len(groups),1/len(groups)),size=100) for _ in range(100)])
    for cp,name in enumerate(["recall","full_support"]):
        results={}
        for a,b in [("votes_dp","mean_dp"),("votes_dp","mean_greedy"),("hamming_dp","mean_dp"),("votes_greedy","mean_greedy")]:
            dif=np.zeros((len(groups),3));win=loss=tie=0
            for t,m in obs.values():
                delta=np.asarray(m[cp][a])-m[cp][b]
                win+=delta[0]>0;loss+=delta[0]<0;tie+=delta[0]==0
                dif[ind[t]]+=delta
            means=dif.sum(0)/counts.sum()*[100,100,1]
            v=(samples@dif)/(samples@counts)[:,None]*[100,100,1]
            ci=np.percentile(v,[2.5,97.5],axis=0)
            assert np.allclose(res[name]["contrasts"][a][b],[means[0],*ci[:,0]])
            results[a+" vs "+b]=dict(delta=means.tolist(),lo=ci[0].tolist(),hi=ci[1].tolist(),win=int(win),loss=int(loss),tie=int(tie))
        ex[name]=results
    put(D/"results.json",res);put(D/"paired.json",ex)
    put(D/"evaluation-seal.json",dict(gold=sha(gold),outcomes=sha(D/"outcomes.json.gz"),results=sha(D/"results.json"),paired=sha(D/"paired.json"),packets=sha(D/"packets.json.gz"),source=sha(Path(__file__)),upstream_analysis=sha(P/"grade_packets.py")))
    for k in res:print(k,{a:res[k]["means"][a] for a in ["mean_dp","votes_dp","hamming_dp","mean_greedy","votes_greedy"]},ex[k]["votes_dp vs mean_dp"])
if __name__=="__main__":main()


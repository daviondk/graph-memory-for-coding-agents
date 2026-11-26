import os
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
import json,gzip,hashlib
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent;SEEDS=[17,29,37,41];SALTS=[f"s{i:02d}" for i in range(8)]
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,d):p.write_text(json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n",encoding="utf8")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(out,qs,geom,with_ci):
    ts,j=np.unique([out[q]["t"] for q in qs],return_inverse=True);nn=np.bincount(j);n=len(qs);arms=load(D/"plan.json")["arms"];a=np.array([[[out[q]["values"][z] for z in out[q]["seeds"][str(s)]] for s in SEEDS] for q in qs],dtype=float)
    e,m,l=[a[:,:,i,:] for i in range(3)];g=a[:,:,3:11];t=a[:,:,11:];new=m[:,:,None,:];old=l[:,:,None,:]
    scale=np.array([100,100,1]);labels=["M-G","M-T","M-L","G-L","T-L"];dif=np.stack([new-g,new-t,np.broadcast_to(new-old,g.shape),g-old,t-old],axis=3)
    base={"questions":n,"trajectories":len(ts),"metrics":["FS2048_pp","Coverage2048_pp","selected_tokens"],"contrast_order":labels,"means":{k:(v.mean(axis=(0,1))*scale).tolist() for k,v in [("E",e),("M",m),("L",l),("G",g.mean(2)),("T",t.mean(2))]},"delta":(dif.mean(axis=(0,1,2))*scale).tolist(),"by_encoder":{str(s):(dif[:,i].mean((0,1))*scale).tolist() for i,s in enumerate(SEEDS)},"by_salt":{s:(dif[:,:,i].mean((0,1))*scale).tolist() for i,s in enumerate(SALTS)},"by_encoder_and_salt":{str(s):{z:(dif[:,i,k].mean(axis=0)*scale).tolist() for k,z in enumerate(SALTS)} for i,s in enumerate(SEEDS)}}
    base["choice_support"]={}
    for k,aidx in [("global_choice",0),("target_choice",1)]:
        ix=np.array([geom[out[q]["t"]][k] for q in qs]);dt=dif[ix,:,:,aidx]
        base["choice_support"][k]={"questions":int(ix.sum()),"trajectories":len({out[q]["t"] for q,take in zip(qs,ix) if take}),"conditional_delta":(dt.mean((0,1,2))*scale).tolist()}
    if not with_ci:return base
    nt=len(ts);summed=np.zeros((nt,*dif.shape[1:]));np.add.at(summed,j,dif);summed=summed.reshape(nt,-1)
    rng=np.random.default_rng(361249);rates={k:[] for k in ("trajectory_fixed_seeds_salts","trajectory_encoder_fixed_salts","trajectory_encoder_salt")}
    for _ in range(100):
        ix=rng.integers(nt,size=(100,nt));w=np.stack([np.bincount(k,minlength=nt) for k in ix]);b=(w@summed).reshape(100,4,8,5,3)/(w@nn)[:,None,None,None,None];sidx=rng.integers(4,size=(100,4));sb=b[np.arange(100)[:,None],sidx];si=rng.integers(8,size=(100,8));sboth=sb[np.arange(100)[:,None,None],np.arange(4)[None,:,None],si[:,None,:]]
        rates["trajectory_fixed_seeds_salts"].append(b.mean((1,2)));rates["trajectory_encoder_fixed_salts"].append(sb.mean((1,2)));rates["trajectory_encoder_salt"].append(sboth.mean((1,2)))
    base["ci"]={k:(np.quantile(np.concatenate(v),[.025,.975],axis=0)*scale).tolist() for k,v in rates.items()};return base
def main():
    out=load(D/"outcomes.json.gz");ref=D.parent/"edge_count_control";geom={}
    for i in range(8):geom.update(load(ref/f"edges-{i}.json.gz"))
    keep=sorted(q for q,v in out.items() if v["eligible"] and not v["pilot"]);assert len(keep)==901
    stats_by={"primary":stats(out,keep,geom,True),"all":stats(out,sorted(out),geom,False),"nonpilot":stats(out,sorted(q for q,v in out.items() if not v["pilot"]),geom,False)}
    base=load(D.parent/"multiseed_midpoint/results.json");current=stats_by["primary"];assert np.allclose(current["delta"][2][:2],base["panels"]["transfer4"]["diff"][0],atol=1e-10)
    salts_by={}; src=load(ref/"results.json")["geometry"]
    for f in ("G","T"):salts_by[f]=[{"salt":s,"changed_graphs":src[f]["per_salt"][s]["different_edge_set_traj"],"changed_degrees":src[f]["per_salt"][s]["different_degrees_traj"]} for s in SALTS]
    save(D/"results.json",{"panels":stats_by,"salts_distinct_keys":len(set(SALTS)),"salt_graph_changes":salts_by,"primary":"M-G on FS2048; CI trajectory_encoder_fixed_salts","outcomes":sha(D/"outcomes.json.gz"),"script":sha(D/"summarize_density.py")})
    print(current["means"]);print(current["delta"]);print(current["ci"]["trajectory_encoder_fixed_salts"])
if __name__=="__main__":main()

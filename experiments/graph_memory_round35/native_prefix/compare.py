import os,sys
for tag in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[tag]="1"
import numpy as np
from pathlib import Path
import gzip,json,hashlib
D=Path(__file__).resolve().parent;W=D.parents[1];N=W/"graph_memory_round22/native_multiseed/official580";R=W/"graph_memory_round34/native_comparison";T=D.parent/"calibration_transfer";S=D.parent/"calibration_scale"
ARMS=("full_rgcn","wo_chunk_adjacency");METRICS=("FullSupport2048","Coverage2048");SEEDS=(13,17)
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,z):
    v=(json.dumps(z,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();p.write_bytes(gzip.compress(v,mtime=0) if p.suffix==".gz" else v)
def collect():
    assert sha(T/"manifest.json")=="1362a0233ac04b177b359f6f0e680f92cf9d7ff688d6dcb914919cf0b843aa4e"
    assert sha(S/"manifest.json")=="75c562b1ea3f028731c5e653c20a3698b917fb22f1d0ea15f05fe332fd541cfe"
    for home,files in [(T,("outcomes.json.gz","results.json")),(S,("test-outcomes.json.gz","models.json"))]:
        manifest=load(home/"manifest.json")["files"]
        for file in files:assert sha(home/file)==manifest[file]
    c=load(T/"outcomes.json.gz");d0=load(S/"test-outcomes.json.gz");z={q:dict(t=v["t"],seeds={}) for q,v in c.items()};states={};files={}
    for seed in SEEDS:
        sk=str(seed);a=load(R/f"audit-{seed}.json");arch_file=R/f"outcomes-{seed}.json.gz";assert a["rows"]==sha(arch_file);arch=load(arch_file);assert set(arch)==set(c)==set(d0)
        states[sk]={};inputs={}
        for ar in ARMS:
            h=N/f"seed-{seed}"/ar
            fr=h/"forecast-seal.json";met=h/"metrics.json.gz";fit=h/"fit.json";res=load(h/"results.json");sig=a["native"][ar];se=load(fr)
            assert sha(fr)==sig["predictions"]==res["forecast"] and sha(met)==sig["scores"]==res["metrics"] and sha(fit)==sig["fit"]
            assert se["checkpoint"]==sig["checkpoint"] and se["ft"]==sig["dense_weight"]
            assert all(sha(h/v["file"])==v["sha"] for v in se["receipts"])
            vals=load(met)["graph"];assert set(vals)==set(arch);inputs[ar]=vals;states[sk][ar]=sig
        assert len({k["dense_weight"] for k in states[sk].values()})==1
        for q,base in c.items():
            t=base["t"];cand=base["seeds"][sk]["oof_3894"];base_policy=base["seeds"][sk]["original_R33"];check=arch[q]
            assert d0[q]["t"]==check[0]==t and np.allclose([base_policy[0],base_policy[4]],[check[1][0],check[1][3]])
            if seed==13:assert cand==d0[q]["arms"]["oof_3894"]
            by={"oof_3894":[cand[0],cand[4]]}
            for i,ar in enumerate(ARMS):
                v=inputs[ar][q];assert v["t"]==t;by[ar]=[v["full_support_2048"],v["coverage_2048"]]
                assert np.allclose(by[ar],[check[2+i][0],check[2+i][3]],rtol=0,atol=1e-12)
            z[q]["seeds"][sk]=by
        files[sk]=dict(audit=sha(R/f"audit-{seed}.json"),native_rescored=sha(arch_file))
    p=D/"outcomes.json.gz";put(p,z);put(D/"pair-seal.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),outcomes=sha(p),native=states,
        official_receipts=files,scale_manifest=sha(S/"manifest.json"),transfer_manifest=sha(T/"manifest.json"),count=len(z)))
def summary():
    info=load(D/"pair-seal.json");p=D/"outcomes.json.gz";assert info["outcomes"]==sha(p) and info["protocol"]==sha(D/"PROTOCOL_RU.md")
    data=load(p);q=sorted(data);ts=sorted({data[k]["t"] for k in q});pos={t:i for i,t in enumerate(ts)};ids=np.array([pos[data[k]["t"]] for k in q]);n=np.bincount(ids)
    assert len(q)==2000 and len(ts)==1207
    names=("oof_3894",*ARMS);xx={a:np.array([[data[k]["seeds"][str(s)][a] for s in SEEDS] for k in q]) for a in names}
    res={}
    for group,cols in (("13",[0]),("17",[1]),("both",[0,1])):
        rows={ar:arr[:,cols] for ar,arr in xx.items()};av={ar:arr.mean(axis=(0,1)).tolist() for ar,arr in rows.items()};comparisons={}
        for ar in ARMS:
            cand=rows["oof_3894"];control=rows[ar];diff=cand-control;ns=len(cols);agg=np.zeros((len(ts),ns,2));np.add.at(agg,ids,diff)
            fixed=[];cross=[];rng=np.random.default_rng(3517)
            for _ in range(200):
                ix=rng.integers(len(ts),size=(100,len(ts)));cnt=np.stack([np.bincount(z,minlength=len(ts)) for z in ix])
                v=(cnt@agg.reshape(len(ts),-1)).reshape(100,ns,2)/(cnt@n)[:,None,None]
                fixed.append(v.mean(1));seed=rng.integers(ns,size=(100,ns));cross.append(v[np.arange(100)[:,None],seed].mean(1))
            ci=lambda a:(100*np.quantile(np.concatenate(a),[.025,.975],axis=0)).tolist()
            tab=[[int(((cand[:,:,0]==j)&(control[:,:,0]==k)).sum()) for k in range(2)] for j in range(2)]
            den=np.sqrt(np.prod(np.array(tab).sum(0).astype(float))*np.prod(np.array(tab).sum(1).astype(float)))
            phi=(tab[0][0]*tab[1][1]-tab[0][1]*tab[1][0])/den
            comparisons[ar]=dict(delta_pp=(100*diff.mean(axis=(0,1))).tolist(),ci95_fixed=ci(fixed),ci95_crossed=ci(cross),table=tab,phi=float(phi),
                win_query_seed=(diff>1e-12).sum(axis=(0,1)).tolist(),loss_query_seed=(diff< -1e-12).sum(axis=(0,1)).tolist())
        res[group]=dict(means=av,comparisons=comparisons)
    put(D/"results.json",dict(groups=res,metrics=METRICS,n=len(q),t=len(ts),rows=sha(p),seal=sha(D/"pair-seal.json"),bootstrap="paired 20000, trajectory fixed or crossed with seed"))
    print(json.dumps(res["both"],sort_keys=True))
if __name__=="__main__":collect();summary()
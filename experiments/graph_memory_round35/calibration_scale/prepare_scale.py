from pathlib import Path
import os,sys,sqlite3,hashlib,time
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
D=Path(__file__).resolve().parent;W=D.parents[1];B=W/"graph_memory_round33/budget_loss";sys.path.insert(0,str(B))
import data as b
from data import f,sha,save,load,np
ARCH=W/"graph_memory_round34/interval_witness"
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def fold(t):return int(digest("scale-v1|"+t)[:16],16)%5
def run():
    start=time.perf_counter();split=load(b.OFF/"split.json.gz");tsets={s:{r["t"] for r in rr} for s,rr in split.items()}
    assert all(not tsets[s]&tsets[t] for s,t in (("train","dev"),("train","test"),("dev","test")))
    official={r["q"]:r["t"] for r in split["train"]};prior=load(b.OLD/"prior.json")
    cohort=load(b.COHORT);small={q for v in cohort.values() for q in v["q"]};prids={q for x in prior["inventory"] for q in x["q"]}
    assert not small&prids and set(official)==small|prids
    assert not {official[q] for q in small}&{official[q] for q in prids}
    idx=f.gmod.graph_index();assert set(official.values())<=set(idx)
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3").as_uri()+"?mode=ro",uri=True)
    ret=f.DenseTaskRetriever(encoder=f.Lookup(db,"ft"),device="cpu");rows={};gxs=[];ys=[];zs=[];cs=[];subset=set(cohort["hash64"]["q"])
    orig={r["q"]:r for r in load(b.PRIVATE/"train.json.gz")}
    inventory=[];by={}
    for q,t in official.items():by.setdefault(t,[]).append(q)
    def process(t,p,x,keys,labels):
        assert len(keys)==len(p["pool"])==len(x)
        lookup={k:i for i,k in enumerate(keys)};pool=tuple(f.TextCandidate.model_validate(v) for v in p["pool"])
        role=b.relative(x,True);gx=np.column_stack((x,role));shape=sorted(p["pool"],key=lambda z:z["item_id"])
        assert all(keys[i]==v["item_id"] and int(v["metadata"]["token_count"])==int(round(np.expm1(x[i,1]))) for i,v in enumerate(shape))
        qmap={z["q"]:z for z in p["qs"]};assert set(qmap)==set(by[t])
        for q in sorted(qmap):
            rec=qmap[q];pos=set(rec["positive"]);ordered=[r.node_id for r in ret.rank(f.TextRankingRequest(task_id=q,query_text=rec["text"],candidates=pool))]
            ix=[lookup[k] for k in ordered];yy=np.array([k in pos for k in ordered]);n=len(ix);assert 0<yy.sum()<n
            if q in labels:assert labels[q].tolist()==[k in pos for k in keys]
            rr=gx[ix];cost=np.rint(np.expm1(rr[:,1])).astype('int32');z=np.column_stack((np.log1p(np.arange(1,n+1)),rr[:,1],rr[:,0],rr[:,1]*rr[:,0]))
            if q in orig:
                assert np.allclose(z,orig[q]["x"]) and np.flatnonzero(yy).tolist()==orig[q]["y"]
                off=f.lin(b.MODEL,rr)+f.lin(b.RANK,f.rank_x(n))
                assert np.allclose(off,orig[q]["o"],atol=1e-10)
            rows[q]=dict(t=t,fold=fold(t),n=n,small=q in small,prior=q in prids,rank_fit=q in subset)
            gxs.append(rr);ys.append(yy);zs.append(z);cs.append(cost)
    # save order explicitly; JSON writers normally sort keys alphabetically.
    for i,pinfo in enumerate(prior["inventory"]):
        path=f.P/f"prior-{i}.npz";assert sha(path)==pinfo["file"];a=np.load(path);xall=a["x"];yall=a["y"]
        qorder=pinfo["q"];offset=0;j=0
        while j<len(qorder):
            t=official[qorder[j]];proj=b.PROJ/"train"/(t+".json.gz");p=load(proj);keys=sorted(v["item_id"] for v in p["pool"]);n=len(keys);base=xall[offset:offset+n];labels={}
            while j<len(qorder) and official[qorder[j]]==t:
                q=qorder[j];assert np.array_equal(base,xall[offset:offset+n]);labels[q]=yall[offset:offset+n];offset+=n;j+=1
            process(t,p,base,keys,labels)
        assert offset==len(xall);inventory.append([path.name,sha(path)]);print("prepared shard",i,len(rows),round(time.perf_counter()-start,1),flush=True)
    for t in sorted({official[q] for q in small}):
        p=load(b.PROJ/"train"/(t+".json.gz"));keys,base=f.shape(p["pool"],f.gmod.project(t,idx));process(t,p,base,keys,{})
    db.close();assert len(rows)==len(set(rows))==3894
    table=D/"numeric-train.npz";np.savez_compressed(table,g=np.vstack(gxs),y=np.concatenate(ys),z=np.vstack(zs),c=np.concatenate(cs))
    qlist=list(rows);p=D/"train-inventory.json";save(p,dict(order=qlist,records=rows,shape=list(np.vstack(gxs).shape),folds={str(k):sum(r["fold"]==k for r in rows.values()) for k in range(5)},
        train_q=len(rows),traj=len(tsets["train"]),dev_q=len(split["dev"]),test_q=len(split["test"]),structural=len(prids),calibration=len(small),rank=len(subset),
        checked_original=len(orig),input_sha=inventory,split=sha(b.OFF/"split.json.gz"),npz=sha(table),npz_bytes=table.stat().st_size,protocol=sha(D/"PROTOCOL_RU.md")))
    print("verified",len(rows),table.stat().st_size,flush=True)
if __name__=="__main__":run()
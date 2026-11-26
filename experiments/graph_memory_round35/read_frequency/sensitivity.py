"""Count logical write batches under fixed read barriers on signed, inert change journals."""
from pathlib import Path
import gzip,hashlib,json,os
for n in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[n]="1"
import numpy as np
D=Path(__file__).resolve().parent;P=D.parent/"deferred_revocation";SOURCE="61a81fd307b1ac9b0e973594100d57b1635061bb087794eaec7986b9c55a2b05"
SCHEDULES=("each_change","g1","g2","g4","g8","g16","actual","terminal")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def put(p,v):
    s=(json.dumps(v,allow_nan=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(s,mtime=0) if p.suffix==".gz" else s)
def schedules(rec):
    a={k:set() for k in SCHEDULES};end=None
    for step,group,actual,plus,minus in rec["log"]:
        if plus or minus:a["each_change"].add(step)
        if actual:a["actual"].add(step)
        if group:
            if group==rec["groups"]:end=step
            for k in (1,2,4,8,16):
                if not group%k:a["g"+str(k)].add(step)
    assert end is not None and end in a["actual"] and all(not (up or dn) for j,_,_,up,dn in rec["log"] if j>end)
    for schedule in a.values():schedule.add(end)
    assert a["actual"]=={r["step"] for r in rec["cuts"].values()}
    return a
def one(rec,barriers):
    truth=set();db=set();pending=set();seen_add=set();peak=rows=packs=cancellations=insert=queued=reads=work=0;at_reads=[]
    for step,_,_,plus,minus in rec["log"]:
        up,down=set(plus),set(minus);assert not up&truth and down<=truth and not up&down
        truth=(truth|up)-down
        work+=bool(up or down);cancellations+=len(up&pending);pending-=up
        insert+=len(up-db);db|=up;queued+=len(down);pending|=down;peak=max(peak,len(pending));seen_add|=up
        assert db-pending==truth and not truth&pending
        if step in barriers:
            reads+=1;at_reads.append(len(pending))
            if pending:packs+=1;rows+=len(pending);db-=pending;pending.clear()
            assert db==truth
    assert not pending and reads==len(barriers) and rows+cancellations==queued
    return dict(reads=reads,batches=packs,nonempty_reads=sum(x>0 for x in at_reads),deleted_rows=rows,inserted_rows=insert,
        queued=queued,reactivated=cancellations,peak=peak,terminal_pending=len(pending),logical_change_events=work,read_batch_sizes=at_reads)
def main():
    assert sha(P/"manifest.json")==SOURCE;fs=load(P/"manifest.json")["files"];out={}
    for i in range(8):
        p=P/f"operations-{i}.json.gz";assert sha(p)==fs[p.name]
        for t,rec in load(p).items():
            assert t not in out;opt=schedules(rec);cur={s:one(rec,barriers) for s,barriers in opt.items()}
            exact=rec["states"]["exact"];lazy=rec["states"]["lazy_read"]
            assert cur["each_change"]["batches"]==exact["batches"] and cur["each_change"]["deleted_rows"]==exact["removed"]
            assert cur["actual"]["batches"]==lazy["batches"] and cur["actual"]["peak"]==lazy["peak"]
            assert cur["g4"]["batches"]==rec["states"]["periodic4"]["drained_batches"]
            assert cur["terminal"]["batches"] in (0,1)
            ladder=("g1","g2","g4","g8","g16","terminal")
            assert all(cur[k]["batches"]>=cur[n]["batches"] for k,n in zip(ladder,ladder[1:]))
            out[t]=dict(groups=rec["groups"],eager=dict(batches=exact["batches"],deleted_rows=exact["removed"],inserts=exact["inserts"]),policies=cur)
    assert len(out)==1207;p=D/"per-trajectory.json.gz";put(p,out);summarize(out,p)
def summarize(out,p):
    ts=sorted(out);metrics=("reads","batches","nonempty_reads","deleted_rows","inserted_rows","queued","reactivated","peak","terminal_pending","logical_change_events")
    arr=np.array([[[out[t]["policies"][m][k] for k in metrics] for m in SCHEDULES] for t in ts]);base=np.array([out[t]["eager"]["batches"] for t in ts]);bi=metrics.index("batches")
    rng=np.random.default_rng(35355);res=[]
    for _ in range(100):
        sample=rng.integers(len(ts),size=(100,len(ts)));mult=np.stack([np.bincount(z,minlength=len(ts)) for z in sample]);res.append((mult@arr[:,:,bi])/(mult@base)[:,None])
    ci=np.quantile(np.concatenate(res),[.025,.975],axis=0);stats={}
    for j,m in enumerate(SCHEDULES):
        rate=arr[:,j,bi]/np.maximum(base,1);has=base>0;raw=[x for t in ts for x in out[t]["policies"][m]["read_batch_sizes"]];nonempty=[x for x in raw if x]
        stats[m]=dict(total={k:int(arr[:,j,i].sum()) for i,k in enumerate(metrics)},ratio=float(arr[:,j,bi].sum()/base.sum()),ratio_ci=ci[:,j].tolist(),
            trajectories_nonempty=int((arr[:,j,bi]>0).sum()),per_trajectory={k:dict(zip(("min","p25","p50","p75","p95","p99","max"),np.quantile(arr[:,j,i],[0,.25,.5,.75,.95,.99,1]).tolist())) for i,k in enumerate(metrics)},
            within_trace_ratio_when_eager_positive=dict(n=int(has.sum()),quartiles=np.quantile(rate[has],[0,.25,.5,.75,1]).tolist()),
            positive_batch_size=dict(n=len(nonempty),min=int(min(nonempty)),median=float(np.median(nonempty)),max=int(max(nonempty))))
    put(D/"results.json",dict(trajectories=len(ts),groups=sum(out[t]["groups"] for t in ts),eager_batches=int(base.sum()),schedules=stats,
        read_log=sha(p),source_manifest=SOURCE,protocol=sha(D/"PROTOCOL_RU.md"),code=sha(Path(__file__))))
    print({k:[v["total"]["reads"],v["total"]["batches"],v["per_trajectory"]["peak"]["max"]] for k,v in stats.items()})
if __name__=="__main__":main()
"""Disjoint 1,024-episode replication of the prespecified eight-query primary workload."""
from pathlib import Path
import random
import shutil
from tempfile import TemporaryDirectory
from time import perf_counter_ns as clock
import numpy as np
from source import ROOT,SCRATCH,SALT,PANELS,blocks,read,schedule,sha,write
from engine import connect,create_base,setup,statement
from study import execute_block,state_digest,size

def replication_blocks(data):
    panels={p:sorted((i for i,e in enumerate(data) if e["panel"]==p),
           key=lambda i:sha((SALT+"|"+p+"|"+data[i]["q"]).encode()))[256:512] for p in PANELS}
    result=[]
    for i in range(32):
        group=[q for p in PANELS for q in panels[p][8*i:8*(i+1)]]
        random.Random(528810+i).shuffle(group);result.append(group)
    orig={data[q]["digest"] for ids in blocks(data) for q in ids}
    new={data[q]["digest"] for ids in result for q in ids}
    assert not (orig & new) and len(new)==1024
    return result

def analyze(timings):
    rng=np.random.default_rng(528993);r=rng.integers(8,size=(10000,8));b=rng.integers(32,size=(10000,32))
    plans={};sample={}
    for plan in ("partial","eligible","journal"):
        t=sorted((x for x in timings if x["plan"]==plan),key=lambda x:x["rep"])
        assert len(t)==8
        a=np.array([[x["blocks"][str(i)][0] for i in range(32)] for x in t])
        setup_ns=np.array([x["build_ns"] for x in t]);ck=np.array([x["checkpoint_ns"] for x in t])
        total=a.sum(axis=1)+setup_ns+ck
        plans[plan]=dict(ms=total.mean()/1e6,warm_ms=a.sum(axis=1).mean()/1e6,setup_ms=setup_ns.mean()/1e6,
            ck_ms=ck.mean()/1e6,reps=(total/1e6).tolist(),disk=t[0]["bytes"],history=t[0]["history"])
        sample[plan]=(a[r[:,:,None],b[:,None,:]].sum(axis=2)+setup_ns[r]+ck[r]).mean(axis=1)
    contrasts={}
    for base in ("partial","eligible"):
        ratio=plans[base]["ms"]/plans["journal"]["ms"]
        contrasts[base]=dict(ratio=ratio,ci=list(np.quantile(sample[base]/sample["journal"],[.025,.975])),
             wins=sum(x>y for x,y in zip(plans[base]["reps"],plans["journal"]["reps"])))
    return dict(plans=plans,contrasts=contrasts)

def main():
    data=read("workload.json.gz");bs=replication_blocks(data);groups=schedule(data,bs)
    names=["REPLICATION_PROTOCOL_RU.md","replicate.py","engine.py","study.py","source.py","workload.json.gz"]
    write("replication-seal.json",{f:sha((ROOT/f).read_bytes()) for f in names})
    timings=[];digests=set()
    with TemporaryDirectory(dir=SCRATCH) as tmp:
        tmp=Path(tmp);base=tmp/"base.db";dest=tmp/"arm.db"
        create_base(base,[(q,data[q]) for ids in bs for q in ids])
        for rep in range(8):
            order=list(range(32));random.Random(528991+rep).shuffle(order)
            plans=["partial","eligible","journal"];random.Random(528990+rep).shuffle(plans)
            for pos,plan in enumerate(plans):
                shutil.copyfile(base,dest)
                db=connect(dest)
                try:
                    db.execute("SELECT sum(b+u) FROM c").fetchone();db.execute("SELECT sum(q) FROM cursor").fetchone()
                    t=clock();setup(db,plan);assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]==0
                    build=clock()-t
                    for live in (True,False):
                        db.execute("EXPLAIN QUERY PLAN "+statement(plan,live),(0,1)).fetchall()
                    size(db)
                    times={str(i):execute_block(db,plan,8,groups[i]) for i in order}
                    t=clock();assert db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]==0;ck=clock()-t
                finally:db.close()
                db=connect(dest)
                try:
                    digest=state_digest(db);digests.add(digest)
                    for ids in bs:
                        for q in ids:
                            assert db.execute(statement(plan,True),(q,data[q]["cuts"])).fetchone()[0]==data[q]["terminal"]
                    count=db.execute("SELECT count(*) FROM history").fetchone()[0] if plan=="journal" else None
                finally:db.close()
                timings.append(dict(rep=rep,position=pos,plan=plan,block_order=order,blocks=times,build_ns=build,
                               checkpoint_ns=ck,identity=digest,bytes=dest.stat().st_size,history=count))
                dest.unlink()
    assert len(digests)==1
    write("replication-timings.json.gz",timings)
    summary=analyze(timings)
    summary.update(episodes=sum(map(len,bs)),reveals=sum(map(len,groups)),edges=sum(len(e[2]) for g in groups for e in g),
                   schedule=sha(str(groups).encode()))
    write("replication.json",summary)
    print(summary["contrasts"])

if __name__=="__main__":
    main()

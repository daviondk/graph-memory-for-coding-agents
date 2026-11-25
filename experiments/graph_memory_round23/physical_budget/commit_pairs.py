"""Counterbalance durable commits per question across independent, identically initialized stores."""
from contextlib import ExitStack
from pathlib import Path
import random,shutil
import bench as b
from bench import g,D,PRIVATE

MODES=("rebuild","cost_certificate","repair")
def guard(c,q,core,budget,prev,mut):
    if not mut:return prev,0
    assert len(mut)==1
    old,new=mut[0]
    if old[1] not in {r[1] for r in prev}:
        left=budget-sum(r[1] for r in core)
        for r in prev:
            if g.key(r)>=g.key(new):break
            left-=r[2]
        if new[2]>left:return prev,0
    return g.rebuild(c,q,core,budget)
def main():
    data=b.fixture();rows=[];sizes={};rng=random.Random(37)
    for rep in range(3):
        conns={};paths={}
        for m in MODES:
            p=PRIVATE/f"paired-{rep}-{m}.sqlite"
            if p.exists():raise RuntimeError("Refusing to replace an existing durable trial DB: "+str(p))
            shutil.copyfile(b.DB,p);c=b.connection(p);c.execute("pragma journal_mode=WAL");c.execute("pragma wal_autocheckpoint=0")
            c.execute("delete from answers where budget!=2048");c.execute("pragma wal_checkpoint(truncate)")
            c.execute("select sum(c) from blocks indexed by idx_priority").fetchone();c.execute("select sum(length(body)) from answers").fetchone()
            conns[m]=c;paths[m]=p
        indices=list(range(192));rng.shuffle(indices)
        for i in indices:
            r=data[i];budget=2048;source=[g.row(v) for v in r["items"]];prev=g.greedy(source,r["core"],budget)
            mut=g.changes(r["items"],prev,"random1",r["q"],budget)
            after={v[1]:v for v in source}
            for _,new in mut:after[new[1]]=new
            expected=g.greedy(after.values(),r["core"],budget);order=list(MODES);rng.shuffle(order)
            for slot,m in enumerate(order):
                c=conns[m];tic=b.clock();c.execute("begin immediate");g.write(c,i,mut);data_ns=b.clock()-tic;st=b.clock()
                if m=="rebuild":
                    new,n=g.rebuild(c,i,r["core"],budget);written=b.store_full(c,i,budget,new)
                else:
                    old,bytes_in=g.cached(c,i,budget)
                    if m=="repair":new,n,_=g.repair(c,i,r["core"],budget,old,mut)
                    else:new,n=guard(c,i,r["core"],budget,old,mut)
                    written=g.persist(c,i,budget,old,new)
                cache=b.clock()-st;st=b.clock();c.execute("commit");commit=b.clock()-st;total=b.clock()-tic
                assert new==expected
                rows.append([rep,i,m,slot,data_ns,cache,commit,total,n,written])
        for m,c in conns.items():
            file=Path(str(paths[m])+"-wal");sizes[f"{rep}/{m}"]=file.stat().st_size
            c.execute("pragma wal_checkpoint(truncate)");c.close()
    b.save(D/"paired-commits.json.gz",rows)
    b.save(D/"paired-commits.json",{"timed":len(rows),"file":b.sha(D/"paired-commits.json.gz"),"wal":sizes,
        "source":b.sha(Path(__file__)),"format":["rep","q","mode","randomized_slot","update_ns","cache_ns","COMMIT_FULL_ns","total_ns","indexed_rows","cached_blob_bytes"]})
if __name__=="__main__":main()


"""First access after SQLite reopen versus a persistent warm connection for the primary edit."""
from random import Random
import bench as b
from bench import g
def main():
    data=b.fixture();rng=Random(29);out=[]
    for mode in ("reopen","warm"):
        conn=b.connection();conn.execute("select sum(c) from blocks indexed by idx_priority").fetchone()
        for rep in range(3):
            indices=list(range(len(data)));rng.shuffle(indices)
            for i in indices:
                r=data[i];budget=2048;ref=g.greedy([g.row(v) for v in r["items"]],r["core"],budget)
                mut=g.changes(r["items"],ref,"random1",r["q"],budget)
                after={v[0]:g.row(v) for v in r["items"]}
                for _,v in mut:after[v[1]]=v
                expected=g.greedy(after.values(),r["core"],budget)
                methods=["rebuild","repair"];rng.shuffle(methods)
                for m in methods:
                    c=b.connection() if mode=="reopen" else conn
                    st=b.clock();c.execute("savepoint one_mutation");g.write(c,i,mut);dt=b.clock()-st
                    st=b.clock()
                    if m=="rebuild":
                        got,rows=g.rebuild(c,i,r["core"],budget)
                        written=b.store_full(c,i,budget,got);kind="full"
                    else:
                        prior,_=g.cached(c,i,budget)
                        got,rows,kind=g.repair(c,i,r["core"],budget,prior,mut)
                        written=g.persist(c,i,budget,prior,got)
                    elapsed=b.clock()-st
                    assert got==expected
                    out.append([mode,rep,i,m,dt,elapsed,rows,written,kind])
                    c.execute("rollback to one_mutation");c.execute("release one_mutation")
                    if mode=="reopen":c.close()
        conn.close()
    b.save(b.D/"first-access.json.gz",out)
if __name__=="__main__":main()


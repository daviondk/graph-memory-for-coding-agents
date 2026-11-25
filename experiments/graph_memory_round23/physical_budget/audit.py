"""Recompute all algorithmic outputs in an independent in-memory DB and audit the published counters."""
from collections import defaultdict
import hashlib,json,sqlite3,sys
import bench as b
from bench import D,g,read,save,sha

def sig(items):
    return hashlib.sha256(json.dumps(items,separators=(",",":")).encode()).hexdigest()
def run():
    raw=read(D/"dynamic-rep1.json.gz")
    seen={(r[1],r[2],r[3],r[4]):r for r in raw}
    c=sqlite3.connect(":memory:",isolation_level=None)
    c.execute("create table blocks(q integer,j integer,neg real,c integer,e integer,l integer,h integer,unique(q,j))")
    c.execute("create index idx_priority on blocks(q,neg,j,c,e,l,h)")
    receipts=[]
    for i,r in enumerate(b.fixture()):
        items=[g.row(v) for v in r["items"]];core=r["core"]
        c.executemany("insert into blocks values(?,?,?,?,?,?,?)",[(i,v[1],v[0],*v[2:]) for v in items])
        for B in g.BUDGETS:
            base=g.greedy(items,core,B)
            assert base==g.rebuild(c,i,core,B)[0]
            if B==2048:assert [v[1] for v in base]==r["strict2048"]
            for case in g.CASES:
                c.execute("savepoint x");old=base;mut=g.changes(r["items"],base,case,r["q"],B)
                if case=="insert1":
                    j=mut[0][1][1];c.execute("delete from blocks where q=? and j=?",(i,j))
                    old=g.greedy([v for v in items if v[1]!=j],core,B)
                new={v[1]:v for v in items}
                for _,v in mut:new[v[1]]=v
                want=g.greedy(new.values(),core,B)
                g.write(c,i,mut);reb,nfull=g.rebuild(c,i,core,B);actual,nnew,branch=g.repair(c,i,core,B,old,mut)
                assert actual==reb==want
                rr=seen[i,B,case,"repair"];fr=seen[i,B,case,"rebuild"]
                assert rr[5:7]==[branch,len(mut)] and rr[9]==nnew and fr[9]==nfull
                a=[v[1] for v in old];z=[v[1] for v in want]
                assert rr[13]==(a!=z) and rr[12]==(old!=want)
                receipts.append([i,B,case,sig(a),sig(z),sig(old),sig(want),nfull,nnew,branch])
                c.execute("rollback to x");c.execute("release x")
    c.close();return receipts
def main():
    rows=run();p=D/"outcome-hashes.json.gz"
    if "--write" in sys.argv:save(p,rows)
    assert read(p)==rows and len(rows)==4608
    r=read(D/"results.json");assert all(sha(D/n)==h for n,h in r["files"].items())
    assert read(D/"native-check.json")["mismatches"]==0 and read(D/"adversarial.json")["mismatches"]==0
    for n in (2,3):
        a=read(D/f"dynamic-rep{n}.json.gz");ref={(v[0],v[1],v[2]):v for v in rows}
        for z in a:
            key=(z[1],z[2],z[3]);x=ref[key]
            assert z[9]==x[8 if z[4]=="repair" else 7] and z[13]==(x[3]!=x[4])
    print("Verified 768 initial and 4608 changed packings, 27648 measured update outputs, 192 distinct trajectories.")
if __name__=="__main__":main()


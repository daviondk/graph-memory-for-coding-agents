"""Independent SQL reference, real query-plan call counts and volatile restart tests."""
import argparse
from collections import Counter,deque
import hashlib
from pathlib import Path
import random
import sqlite3
from tempfile import TemporaryDirectory

from reader import Hot,MODES,Reader
from experiment import HERE,load,save


def sql_rank(db,f):
    return db.execute("""WITH votes AS (
        SELECT b.f,count(*) AS n FROM posting a JOIN posting b ON a.j=b.j
        WHERE a.f=? AND b.f<>a.f GROUP BY b.f)
        SELECT c.f,ifnull(v.n,0) FROM catalog c LEFT JOIN votes v ON c.f=v.f
        WHERE c.f<>? ORDER BY ifnull(v.n,0) DESC,c.recent DESC,c.f LIMIT 8""",(f,f)).fetchall()


def test(path,mode):
    rng=random.Random(57121)
    db=sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE posting(f,j,PRIMARY KEY(f,j)) WITHOUT ROWID;"
                     "CREATE INDEX by_event ON posting(j,f);CREATE TABLE catalog(f INTEGER PRIMARY KEY,recent);")
    h=Reader(path,mode,True);catalog=Counter();window=deque();schedule=Hot()
    seq=[(0,1,7),(0,1),(0,2,3),(0,2),(0,3),(0,4),(0,1),(0,5),(0,6),(0,2),(0,2),(0,3)]
    seq.extend((0,1) if j%5 else (j+15,1,2) for j in range(40))
    seq.extend(tuple(sorted(rng.sample(range(20),2+j%5))) for j in range(55))
    stats=Counter();sha=hashlib.sha256()
    for j,ids in enumerate(seq):
        if j in (10,39,64):
            h.close();h=Reader(path,mode)
            schedule=Hot()
            assert not h.store.restore_rows and not h.store.restore_payload
            if h.hot:assert not h.hot.live and not h.hot.owned
            if h.lru:assert not h.lru.maps
            stats["cold_reopens"]+=1
        tie=dict(catalog);prior=sorted(catalog,key=lambda g:(-catalog[g],g))[:9]
        queries=list(catalog)+[-1]
        rng.shuffle(queries)
        for f in queries:
            selects=[]
            h.db.set_trace_callback(lambda statement:selects.append(statement) if statement.lstrip().upper().startswith("SELECT") else None)
            actual,work=h.read(f,tie,prior)
            h.db.set_trace_callback(None)
            exact=sql_rank(db,f)
            assert actual==exact and len(selects)==work[0]+work[3],(mode,j,f,actual,exact,selects,work)
            sha.update(repr((j,f,actual)).encode())
            stats["independent_rankings"]+=1
            stats["instrumented_sql_calls"]+=len(selects)
            if h.lru:assert h.lru.charge<=h.lru.budget
        rev=hashlib.sha1(str(j).encode()).hexdigest()
        if j in (1,10,12,39,65,72):
            try:h.append(j,rev,ids,0,True)
            except RuntimeError:pass
            else:raise AssertionError("failure not injected")
            assert h.store.next_id==j
            for f in queries:
                assert h.read(f,tie,prior)[0]==sql_rank(db,f)
                stats["post_fault_rankings"]+=1
            stats["rollbacks"]+=1
        schedule.append(j,ids)
        assert h.append(j,rev,ids,schedule.budget()) and not h.append(j,rev,ids,schedule.budget())
        try:h.append(j,rev,ids[::-1],schedule.budget())
        except ValueError:pass
        else:raise AssertionError("conflicting retry accepted")
        stats["idempotent_retries"]+=1;stats["conflicts"]+=1
        if len(window)==32:catalog.subtract(window.popleft())
        window.append(ids);catalog.update(ids)
        db.executemany("INSERT INTO posting VALUES(?,?)",((f,j) for f in ids))
        db.executemany("INSERT OR REPLACE INTO catalog VALUES(?,?)",catalog.items())
    assert h.db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    h.close();db.close()
    return dict(counters=dict(stats),answer_digest=sha.hexdigest())


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    with TemporaryDirectory(dir=HERE,prefix="checks-") as td:
        results={mode:test(Path(td)/(mode+".sqlite"),mode) for mode in MODES}
    assert len({r["answer_digest"] for r in results.values()})==1
    if args.verify:assert results==load(HERE/"correctness.json")
    else:save(HERE/"correctness.json",results)
    print({m:r["counters"]["independent_rankings"] for m,r in results.items()})


if __name__=="__main__":
    main()

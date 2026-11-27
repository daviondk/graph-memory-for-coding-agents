"""Rollback, process death on seal, replay and reconstruction against independent oracles."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import random
import sqlite3
import sys
import os
from tempfile import TemporaryDirectory
import subprocess

from bench import factory as base_factory, HERE, load, panels, prepare, save
from block_store import ARMS, EXTRA, TAIL_MODES, BLOCK, unpack
from frame_store import FRAME_MODES, FrameStore
from slab_store import NEW_MODES, SlabStore


def factory(path, mode, create=False):
    if mode in FRAME_MODES:return FrameStore(path,mode,create)
    if mode in NEW_MODES:return SlabStore(path,mode,create)
    return base_factory(path,mode,create)


def sql_state(st):
    names=[name for name, in st.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {n:st.db.execute("SELECT * FROM "+n+" ORDER BY 1,2").fetchall() for n in names}



def revision(j):
    return hashlib.sha1(f"source event {j}".encode()).hexdigest()


def sample(n):
    rng=random.Random(57062)
    for j in range(n):
        # Global hub, stable pair, low-frequency files, never-before-seen files, high IDs.
        pool=list(range(3,min(63,7+j)))+[129,16385,100000+j]
        nodes=[0,1] if j%9 else [0,2]
        nodes.extend(rng.sample(pool,min(1+j%6,len(pool))))
        yield (j, revision(j), tuple(nodes))


def reject(call,exception,word):
    try:call()
    except exception as err: assert word in str(err)
    else:raise AssertionError("unexpectedly committed")


def authoritative(conn,f):
    return conn.execute("""SELECT g.f,COALESCE(x.score,0) FROM file g LEFT JOIN
        (SELECT b.f,count(*) AS score FROM member a JOIN member b ON a.j=b.j
         WHERE a.f=? GROUP BY b.f) x ON x.f=g.f
        WHERE g.f<>? ORDER BY COALESCE(x.score,0) DESC,g.freq DESC,g.f LIMIT 8""",(f,f)).fetchall()


def synthetic(path,mode):
    sql=sqlite3.connect(":memory:")
    sql.executescript("CREATE TABLE file(f INTEGER PRIMARY KEY,freq INTEGER);"
                      "CREATE TABLE member(f INTEGER,j INTEGER,PRIMARY KEY(f,j)); CREATE INDEX by_j ON member(j,f);")
    freq=Counter()
    st=factory(path,mode,True)
    out=Counter()
    for j,rev,ids in sample(196):
        if j in (0,1,62,63,64,65,126,127,128,191,192):
            st.close();st=factory(path,mode)
            assert st.next_id==j
            if mode in (*TAIL_MODES,"slab_sealed_list"):assert st.restore_rows==j%BLOCK
            out["reopens"]+=1
        prior=sorted(freq,key=lambda f:(-freq[f],f))[:9]
        if j in (2,63,64,127,191):
            before=sql_state(st)
            reject(lambda:st.append(j,rev,ids,True),RuntimeError,"rollback")
            after=sql_state(st)
            assert before==after and st.next_id==j
            out["full_rollback_snapshots"]+=1
        if j in (1,62,63,64,127,128,191,192,195):
            for f in [*sorted(freq),-1]:
                ranking,_=st.read(f,freq,prior)
                assert ranking==authoritative(sql,f),(mode,j,f)
                out["sql_preappend_rankings"]+=1
        assert st.append(j,rev,ids) and not st.append(j,rev,ids)
        reject(lambda:st.append(j,revision(j+1000),ids),ValueError,"conflicting")
        reject(lambda:st.append(j,rev,ids[::-1]),ValueError,"conflicting")
        reject(lambda:st.append(j+2,rev,ids),ValueError,"gap")
        out["idempotent_retries"]+=1;out["conflicting_retries"]+=2;out["gaps"]+=1
        freq.update(ids)
        sql.executemany("INSERT INTO member VALUES(?,?)",((f,j) for f in ids))
        sql.executemany("INSERT OR REPLACE INTO file VALUES(?,?)",((f,freq[f]) for f in ids))
    if mode in (*NEW_MODES,*FRAME_MODES):
        source=((j,*st.get_event(j)) for j in range(st.next_id))
    else:
        source=st.db.execute("SELECT j,rev,members FROM event ORDER BY j")
    for row,event in zip(source,sample(196),strict=True):
        assert (row[0],row[1].hex(),unpack(row[2]))==event
        out["decoded_source_body_revisions"]+=1
    st.close();sql.close()
    return dict(out)


def crash_child(path,mode):
    st=factory(path,mode)
    st.db.create_function("crash_during_insert",0,lambda:os._exit(73))
    st.db.execute("CREATE TEMP TRIGGER crash BEFORE INSERT ON posting BEGIN SELECT crash_during_insert(); END")
    j,rev,ids=list(sample(BLOCK))[-1]
    st.append(j,rev,ids)
    raise RuntimeError("trigger did not fire")


def crashcheck(path,mode):
    st=factory(path,mode,True)
    stream=list(sample(BLOCK+1))
    for e in stream[:BLOCK-1]: st.append(*e)
    st.close()
    proc=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),"--child",str(path),mode])
    assert proc.returncode==73,(mode,proc.returncode)
    st=factory(path,mode)
    assert st.next_id==BLOCK-1
    if mode in (*TAIL_MODES,"slab_sealed_list"): assert st.restore_rows==BLOCK-1
    for e in stream[BLOCK-1:]: assert st.append(*e)
    st.close();st=factory(path,mode)
    assert st.next_id==BLOCK+1 and st.db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    freq=Counter(f for _,_,nodes in stream for f in nodes)
    prior=sorted(freq,key=lambda f:(-freq[f],f))[:9]
    for f in freq:
        historical=Counter(x for _,_,nodes in stream if f in nodes for x in nodes if x!=f)
        expected=sorted((g for g in freq if g!=f),key=lambda g:(-historical[g],-freq[g],g))[:8]
        assert st.read(f,freq,prior)[0]==[(g,historical[g]) for g in expected]
    st.close();return dict(crash_exit_code=proc.returncode,post_recovery_rankings=len(freq))


def replay_real(path,mode,ops):
    st=factory(path,mode,True)
    total=sum(op[0]=="w" for op in ops)
    split=total//2
    n=checks=post=0
    reopened=False
    for op in ops:
        if n>=split and not reopened:
            st.close();st=factory(path,mode);reopened=True
            assert st.next_id==n
            if mode in (*TAIL_MODES,"slab_sealed_list"):assert st.restore_rows==n%BLOCK
        if op[0]=="q":
            _,f,tie,prior,expected=op
            assert st.read(f,tie,prior)[0]==expected
            checks+=1;post+=int(reopened)
        else:
            assert st.append(*op[1:]);n+=1
    writes=(op for op in ops if op[0]=="w")
    if mode in (*NEW_MODES,*FRAME_MODES):
        returned=((j,*st.get_event(j)) for j in range(st.next_id))
    else:
        returned=st.db.execute("SELECT j,rev,members FROM event ORDER BY j")
    receipts=0
    for op,row in zip(writes,returned,strict=True):
        _,j,rev,ids=op
        assert (row[0],row[1].hex(),unpack(row[2]))==(j,rev,tuple(ids))
        receipts+=1
    assert receipts==n
    st.close()
    return dict(events=n,rankings=checks,after_restart=post,source_receipts=receipts)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--storage",action="store_true");ap.add_argument("--child",nargs=2);ap.add_argument("--verify",action="store_true");args=ap.parse_args()
    if args.child:
        crash_child(*args.child);return
    raw=panels()
    inputs={(p,repo):prepare(rows,p)[0] for p in ("B","long") for repo,rows in raw[p].items()}
    result={}
    with TemporaryDirectory(dir=HERE,prefix="audit-") as td:
        for mode in ((*NEW_MODES,*FRAME_MODES) if args.storage else (*ARMS,*EXTRA)):
            path=Path(td)/"test.sqlite"
            s=synthetic(path,mode);path.unlink()
            crash=crashcheck(path,mode);path.unlink()
            live={}
            for (p,repo),ops in inputs.items():
                live[p+"/"+repo]=replay_real(path,mode,ops);path.unlink()
            result[mode]=dict(synthetic=s,crash=crash,projects=live)
    dest=HERE/("source-correctness.json" if args.storage else "correctness.json")
    if args.verify:assert result==load(dest)
    else:save(dest,result)
    print({m:r["synthetic"]["sql_preappend_rankings"] for m,r in result.items()})


if __name__=="__main__":
    main()

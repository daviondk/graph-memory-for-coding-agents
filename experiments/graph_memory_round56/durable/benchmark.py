"""Single-writer full-WAL replay on fresh databases. Each checkpointed result can be resumed."""
import argparse
from collections import Counter, defaultdict, deque
import gzip
import hashlib
import json
from pathlib import Path
import platform
import random
import sqlite3
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from store import Store
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"event_intersection"))
from evaluate import chosen, panels

MODES=("full","own","split")
SEED=56045
RAW=HERE/"runs.json.gz"

def save(path, obj):
    data=(json.dumps(obj, sort_keys=True, separators=(",",":"))+"\n").encode()
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)
    temp.replace(path)

def load(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())

def prepare(rows,panel):
    ids={}
    freq=Counter()
    window=deque()
    bits=defaultdict(int)
    ops=[]
    key=hashlib.sha256()
    j=0
    for t,(sha,paths) in enumerate(rows):
        if len(paths)>64:paths=[]
        name=chosen(panel,sha,t,len(rows),paths)
        if name is not None:
            anchor=ids.get(name,-1)
            ranked=sorted(range(len(ids)), key=lambda f:(-freq[f],f))
            prior=ranked[:9]
            scores={f:(bits.get(anchor,0)&bits.get(f,0)).bit_count()
                    for f in range(len(ids)) if f!=anchor}
            expected=sorted(scores.items(),key=lambda x:(-x[1],-freq[x[0]],x[0]))[:8]
            ops.append(("q",anchor,dict(freq),prior,expected))
            key.update(json.dumps([sha,anchor,expected],separators=(",",":")).encode()+b"\n")
        codes=tuple(ids.setdefault(p,len(ids)) for p in paths)
        if len(window)==32:freq.subtract(window.popleft())
        freq.update(codes);window.append(codes)
        if len(codes)>=2:
            for f in codes:bits[f]|=1<<j
            ops.append(("w",j,sha,codes))
            j+=1
    return ops,key.hexdigest()

def inventory(st):
    tables=("event","post","live","cold_file") if st.mode=="split" else ("event","post")
    physical={k:st.db.execute("SELECT COUNT(*) FROM "+k).fetchone()[0] for k in tables}
    if st.mode=="own":
        n=sum(len(tail) for tail,_ in st.owned.values())
        records={j for tail,_ in st.owned.values() for j,_ in tail}
        resident=dict(owner_refs=n,hot_events=len(records),incident_refs=0)
    elif st.mode=="split":
        resident=dict(owner_refs=sum(st.owners.values()),hot_events=len(st.live),
                      incident_refs=sum(len(x) for x in st.incident.values()))
    else:resident=dict(owner_refs=0,hot_events=0,incident_refs=0)
    return dict(tables=physical,ram=resident)

def run(ops,dbpath,mode,repeat_reads):
    start=perf_counter_ns()
    st=Store(dbpath,mode,create=True)
    init=perf_counter_ns()-start
    assert st.db.execute("PRAGMA synchronous").fetchone()==(2,)
    write_ns=read_ns=0
    counts=Counter()
    for op in ops:
        if op[0]=="q":
            _,anchor,tie,prior,expected=op
            for _ in range(repeat_reads):
                start=perf_counter_ns()
                rank,(calls,rows,payload)=st.read(anchor,tie,prior)
                read_ns+=perf_counter_ns()-start
                assert rank==expected,(mode,anchor,rank,expected)
                counts.update(dict(queries=1,sql=calls,rows=rows,payload=payload))
        else:
            _,j,sha,ids=op
            start=perf_counter_ns()
            ok=st.append(j,sha,ids)
            write_ns+=perf_counter_ns()-start
            assert ok
            counts.update(dict(events=1,members=len(ids)))
    assert not st.restore_rows and not st.restore_payload
    inv=inventory(st)
    start=perf_counter_ns()
    result=st.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    checkpt=perf_counter_ns()-start
    assert result==(0,0,0)
    st.close()
    size=dbpath.stat().st_size
    start=perf_counter_ns()
    reopened=Store(dbpath,mode)
    restart=perf_counter_ns()-start
    assert reopened.next_id==counts["events"]
    warm_rows=reopened.restore_rows;warm_payload=reopened.restore_payload
    reopened.close()
    return dict(write_ns=write_ns,read_ns=read_ns,initialize_ns=init,checkpoint_ns=checkpt,
                reopen_ns=restart,restore_rows=warm_rows,restore_payload=warm_payload,bytes=size,
                counts=dict(counts),**inv)

def aggregate(raw):
    out={}
    for panel in ("B","long"):
        for nread in (1,8):
            for mode in MODES:
                batches=[]
                for rep in range(3):
                    ls=[r for r in raw["runs"] if (r["panel"],r["nread"],r["mode"],r["rep"])==(panel,nread,mode,rep)]
                    if not ls:continue
                    assert len(ls)==(6 if panel=="B" else 3)
                    res={k:sum(r[k] for r in ls) for k in ("write_ns","read_ns","initialize_ns","checkpoint_ns","reopen_ns","restore_rows","restore_payload","bytes")}
                    for group in ("counts","tables","ram"):
                        res[group]=dict(sum((Counter(r[group]) for r in ls),Counter()))
                    res["mixed_ns"]=res["write_ns"]+res["read_ns"]
                    batches.append(res)
                if not batches:continue
                entry={}
                for k,v in batches[0].items():
                    values=[b[k] for b in batches]
                    if k.endswith("_ns"):entry[k]={"median":statistics.median(values),"values":values}
                    else:
                        assert all(a==v for a in values)
                        entry[k]=v
                out[f"{panel}-{nread}-{mode}"]=entry
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--repeats",choices=(1,2,3),type=int,default=3)
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    raw=load(RAW) if RAW.exists() else dict(meta=dict(seed=SEED,python=sys.version,system=platform.platform(),sqlite=sqlite3.sqlite_version),runs=[],oracle={})
    data=panels()
    ops={}
    for panel in ("B","long"):
        for repo,rs in data[panel].items():
            actions,sig=prepare(rs,panel)
            assert raw["oracle"].setdefault(panel+"/"+repo,sig)==sig
            ops[panel,repo]=actions
    if args.verify:
        assert len(raw["runs"])==162
        assert aggregate(raw)==load(HERE/"results.json")
        for panel,n in (("B",880),("long",196)):
            for nread in (1,8):
                for mode in MODES:
                    assert load(HERE/"results.json")[f"{panel}-{nread}-{mode}"]["counts"]["queries"]==n*nread
        print("Verified 162 runs and nine independent oracle digests.");return
    jobs=lambda r,rng:[(panel,repo,r,nread,mode) for panel,repo in ops for nread,mode in rng.sample([(n,m) for n in (1,8) for m in MODES],6)]
    rng=random.Random(SEED)
    done={(r["panel"],r["repo"],r["rep"],r["nread"],r["mode"]) for r in raw["runs"]}
    with TemporaryDirectory(dir=HERE,prefix="scratch-") as folder:
        for rep in range(args.repeats):
            for key in jobs(rep,rng):
                if key in done:continue
                panel,repo,_,nread,mode=key
                dbpath=Path(folder)/"run.sqlite"
                result=run(ops[panel,repo],dbpath,mode,nread)
                result.update(panel=panel,repo=repo,rep=rep,nread=nread,mode=mode)
                raw["runs"].append(result)
                dbpath.unlink()
                save(RAW,raw)
            save(HERE/"results.json",aggregate(raw))
            print("Completed",rep+1,"paired repetitions,",len(raw["runs"]),"persisted layouts",flush=True)

if __name__=="__main__":main()

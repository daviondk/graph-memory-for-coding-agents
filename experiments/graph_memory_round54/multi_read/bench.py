"""Registered CPU replay, all-state audits, repetitions and historical-read microbenchmarks."""
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import tempfile
import time

from core import *

W=Path("D:/CodexResearch/x20-r54-multi-read")
REPEAT=7;SEED=540263
def sha(f):
    with f.open("rb") as h:return hashlib.file_digest(h,"sha256").hexdigest()
def save(name,z):
    b=(json.dumps(z,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    (D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)
def load(name):return read(D/name)
def oracle(work):
    refs={};stats=Counter()
    for q,rows in work.items():
        seen=set();edge=Counter();prev=[];versions=[[]]
        for r in rows:
            assert r["sha"]==sig(r["born"],r["delta"]);seen.update(r["born"])
            for a,b,v in r["delta"]:edge[a,b]+=v;assert a in seen and b in seen and edge[a,b]>=0
            # Recompute source weights from all edge intervals at this revision.
            z=Counter()
            for (a,b),w in edge.items():z[a]+=w
            v=sorted(((i,z[i]) for i in seen),key=lambda u:(-u[1],u[0]))[:M]
            assert (list(v[0]) if v else None)==r["winner"]
            stats["snapshot"]+=prev!=v;stats["snapshot_pairs"]+=len(v) if v!=prev else 0
            for typ,g in GROUPS.items():
                if typ=="snapshot":continue
                for a,b in g:
                    if prev[a:b]!=v[a:b]:stats[typ]+=1;stats[typ+"_pairs"]+=len(v[a:b])
            l,h=dict(prev),dict(v)
            stats["admitted"]+=sum(l.get(i)!=u for i,u in h.items())
            stats["closures"]+=sum(h.get(i)!=u for i,u in l.items())
            stats["admitted_same_pair_shift"]+=sum(i in l and l[i]==s and prev.index((i,s))!=j for j,(i,s) in enumerate(v))
            prev=v;versions.append(v)
        refs[q]=versions
    return refs,stats
def prepare():
    w=read(OLD/"workload.json.gz");reg=read(OLD/"registration.json")
    assert reg["work_sha"]==sha(OLD/"workload.json.gz") and len(w)==40
    refs,stats=oracle(w);return w,refs,stats
def schedule(work):
    qs=list(work);stages={}
    for m in (0,1,8):
        batches={}
        for qi,q in enumerate(qs):
            for row in work[q]:
                t=row["t"];batches[q,t]=[(v,KS[(t+qi+i)%3]) for i,v in enumerate(reads(m,q,t))]
        stages[m]=batches
    rnd=random.Random(SEED+1);queries=[]
    for i in range(512):
        q=rnd.choice(qs);queries.append((q,rnd.randrange(len(work[q]))))
    return stages,queries
def storage(db,plan):
    table="packet" if plan in GROUPS else "cv"
    meta={"history_rows":db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0],"pages":db.execute("PRAGMA page_count").fetchone()[0],"page_size":db.execute("PRAGMA page_size").fetchone()[0]}
    if table=="packet":meta["packet_payload_bytes"]=db.execute("SELECT SUM(length(payload)) FROM packet").fetchone()[0]
    try:meta["history_btree_bytes"]=db.execute("SELECT sum(pgsize) FROM dbstat WHERE name IN ('packet','cv','cv_open','cv_best')").fetchone()[0]
    except sqlite3.OperationalError:pass
    return meta
def execute(path,plan,m,work,refs,batch,warm,check=False):
    clock=time.perf_counter_ns;t0=clock()
    db=connect(path);store=Store(db,plan);build=clock()-t0;wr=rd=0
    try:
        for q,events in work.items():
            for r in events:
                t=r["t"];a=clock();ok=store.update(q,r);wr+=clock()-a;assert ok
                requests=batch[q,t]
                if requests:
                    a=clock();actual=[store.get(q,j,k) for j,k in requests];rd+=clock()-a
                    assert actual==[refs[q][j][:k] for j,k in requests]
            if check:
                store.last.clear()
                for j,e in enumerate(refs[q]):
                    for k in KS:assert store.get(q,j,k)==e[:k]
        a=clock();ch=db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone();cp=clock()-a;assert ch[0]==0
        body=dict(build_ns=build,write_ns=wr,read_ns=rd,checkpoint_ns=cp,total_ns=build+wr+rd+cp,bytes=path.stat().st_size)
        if check:
            assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
            body.update(storage(db,plan));sql=QUERIES[len(GROUPS[plan])] if plan in GROUPS else INTERVAL
            vals=("q11",16) if plan in GROUPS else ("q11",16,16,8)
            body["query_plan"]=[z[-1] for z in db.execute("EXPLAIN QUERY PLAN "+sql,vals)]
            if plan in GROUPS:assert all("PRIMARY KEY" in txt for txt in body["query_plan"] if "SEARCH packet" in txt)
            else:assert any("COVERING INDEX cv_best" in txt for txt in body["query_plan"])
        if m==8:
            res={}
            for k in KS:
                for q,v in warm[:64]:store.get(q,v,k)
                a=clock();vals=[store.get(q,v,k) for q,v in warm];spent=clock()-a
                assert vals==[refs[q][v][:k] for q,v in warm];res[str(k)]=spent/len(warm)
            body["warm_ns_per_read"]=res
        return body
    finally:db.close()
def faults(path,plan,work,refs):
    a=connect(path);b=connect(path)
    try:
        primary=Store(a,plan);other=Store(b,plan,False);q="q11"
        for j,row in enumerate(work[q]):
            store=(primary,other)[j%2]
            if row["t"]==17:
                try:store.update(q,row,fault=True)
                except RuntimeError:pass
                else:raise AssertionError("rollback did not fail")
                assert other.get(q,16,8)==refs[q][16]
                try:other.get(q,17,8)
                except ValueError:pass
                else:raise AssertionError("future read succeeded")
            assert store.update(q,row) and not store.update(q,row)
            for k in KS:assert other.get(q,j+1,k)==refs[q][j+1][:k]
        bad=dict(work[q][-1],sha="mismatched")
        try:other.update(q,bad)
        except ValueError:pass
        else:raise AssertionError("conflicting retry accepted")
    finally:a.close();b.close()
def main():
    W.mkdir(exist_ok=True);reg={"work":sha(OLD/"workload.json.gz"),"prior":sha(OLD/"registration.json"),"protocol":sha(D/"PROTOCOL_RU.md"),
        "code":{n:sha(D/n) for n in ("core.py","bench.py")},"plans":PLANS,"k":KS,"max_k":M,"blocks":REPEAT,"seed":SEED,
        "sqlite":sqlite3.sqlite_version,"python":platform.python_version(),"os":platform.platform(),"processor":platform.processor(),
        "clock":time.get_clock_info("perf_counter").resolution,"pid":os.getpid()}
    save("registration.json",reg);work,refs,stats=prepare();stages,warm=schedule(work);runs=[];valid={}
    with tempfile.TemporaryDirectory(dir=W) as path:
        temp=Path(path)
        for plan in PLANS:
            f=temp/(plan+".sqlite");valid[plan]=execute(f,plan,8,work,refs,stages[8],warm,True);faults(temp/(plan+"-fault.sqlite"),plan,work,refs)
        assert all(valid[p]["history_rows"]==stats[p] for p in (*GROUPS,"admitted"))
        save("exactness.json",dict(versions=sum(map(len,refs.values())),k=KS,events=sum(map(len,work.values())),logical=dict(stats),plans=valid))
        print("All historic versions verified",flush=True)
        order=random.Random(SEED)
        for rep in range(REPEAT):
            modes=[0,1,8];order.shuffle(modes)
            for m in modes:
                plans=list(PLANS);order.shuffle(plans)
                for position,p in enumerate(plans):
                    fp=temp/f"repeat-{rep}-{m}-{p}.sqlite"
                    outcome=execute(fp,p,m,work,refs,stages[m],warm)
                    runs.append(dict(rep=rep,m=m,plan=p,position=position,**outcome))
                    fp.unlink()
            print("Block",rep+1,flush=True)
    save("timings.json.gz",runs);save("run-seal.json",dict(registration=sha(D/"registration.json"),times=sha(D/"timings.json.gz"),exactness=sha(D/"exactness.json")))
if __name__=="__main__":main()

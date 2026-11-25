"""Serve identical BM25 queries in isolated processes and measure the controller round trip."""
from collections import OrderedDict,defaultdict
import gzip
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import random
import sqlite3
import sys
from time import perf_counter_ns as now
import zlib

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/"graph_memory_round25/query_view"
sys.path.insert(0,str(SOURCE))
from ranking import bag,select
DATA=Path("D:/CodexResearch/x20-query-projection-sql")
INDEX=DATA/"terms.sqlite"; JOURNAL=DATA/"query-views.sqlite"
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(p,obj):
    raw=(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ro(path):return sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
def order(key):return hashlib.sha256(("worker-locality-v1/"+key).encode()).digest()
def postings(blob):
    # Decode gap/frequency base-128 integers from the persisted R25 B-tree.
    groups={};previous=-1;current=shift=0;pending=None
    for octet in blob:
        current|=(octet&127)<<shift
        if octet&128:shift+=7;continue
        if pending is None:pending=current
        else:
            previous+=pending; groups[previous]=current;pending=None
        current=shift=0
    assert pending is None and shift==0
    return groups
def service(pipe):
    index=ro(INDEX);journal=ro(JOURNAL);cache=OrderedDict()
    pipe.send(os.getpid())
    while True:
        message=pipe.recv()
        if message=="stop":break
        if isinstance(message,str):
            cache.clear();pipe.send(True);continue
        method,capacity,sid,question=message
        start=now();wire=payload=0;miss=int(sid not in cache)
        if miss:
            key,raw=index.execute("SELECT id,header FROM snapshots WHERE name=?",(sid,)).fetchone()
            wire+=len(raw)
            coords,lengths=json.loads(zlib.decompress(raw))
            view={"rows":[{"coords":c,"length":n} for c,n in zip(coords,lengths)]}
            inverted={}
            if method=="raw_cache":
                docs=journal.execute("SELECT idx,body FROM payload WHERE sid=? ORDER BY idx",(sid,))
                for i,body in docs:
                    payload+=len(body)
                    for word,count in bag(body.decode()).items():
                        inverted.setdefault(word,{})[i]=count
                wire+=payload
        else:
            key,view,inverted=cache.pop(sid)
        if method!="raw_cache":
            missing=sorted(set(bag(question))-inverted.keys())
            if missing:
                markers=",".join("?" for _ in missing)
                sql=f"SELECT term,postings FROM terms WHERE id=? AND term IN ({markers})"
                inverted.update({w:{} for w in missing})
                for term,raw in index.execute(sql,(key,*missing)):
                    inverted[term]=postings(raw);wire+=len(term.encode())+len(raw)
        winner=select(view,question,"inverted",None,inverted)
        if method!="shared_sql":
            cache[sid]=(key,view,inverted)
            if len(cache)>capacity:cache.popitem(last=False)
        pipe.send([winner,wire,payload,miss,now()-start])
    index.close();journal.close();pipe.close()
def main():
    db=ro(JOURNAL)
    articles=sorted((r[0] for r in db.execute("SELECT sid FROM snapshot WHERE corpus='squad'")),key=order)
    assert len(articles)==48
    streams={s:sorted(db.execute("SELECT q,question FROM future WHERE sid=?",(s,)),key=lambda r:order(r[0])) for s in articles}
    db.close()
    ref={(r["g"],r["q"]):r["ref"] for r in read(SOURCE/"decisions.json.gz") if r["c"]=="squad"}
    work=[]
    for group in range(0,len(articles),8):
        for step in range(11):
            for slot,sid in enumerate(articles[group:group+8]):
                q,question=streams[sid][step]
                work.append((sid,q,question,slot%4,(slot+step)%4))
    conditions=[(backend,capacity,route) for backend in ("raw_cache","shared_sql","term_cache")
                for capacity in ((4,) if backend=="shared_sql" else (1,4,8)) for route in ("affine","rotate")]
    lock={"script":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md"),"index":sha(INDEX),"journal":sha(JOURNAL),
          "reference":sha(SOURCE/"decisions.json.gz"),"clients":4,"conditions":conditions,
          "order":[[s,q,i,j] for s,q,query,i,j in work]}
    lockfile=HERE/"schedule.json"
    if lockfile.exists():assert read(lockfile)==json.loads(json.dumps(lock))
    else:save(lockfile,lock)
    ctx=mp.get_context("spawn");parents=[];processes=[];log=[]
    try:
        for i in range(4):
            receive,send=ctx.Pipe()
            worker=ctx.Process(target=service,args=(send,));worker.start();send.close()
            processes.append(worker);parents.append(receive)
        pids=[p.recv() for p in parents];assert len(set(pids))==4 and os.getpid() not in pids
        for rep in range(3):
            shuffled=conditions.copy();random.Random(27401+rep).shuffle(shuffled)
            for method,cap,route in shuffled:
                for target in parents:target.send("reset")
                assert all(p.recv() for p in parents)
                for sid,q,question,a,b in work:
                    slot=a if route=="affine" else b
                    target=parents[slot];start=now();target.send((method,cap,sid,question))
                    winner,wire,payload,miss,ns=target.recv();total=now()-start
                    assert winner==ref[sid,q]
                    log.append([rep,method,cap,route,sid,q,slot,winner,wire,payload,miss,ns,total])
            print("completed",rep,flush=True)
    finally:
        for p in parents:p.send("stop")
        for w in processes:w.join(15)
        for p in parents:p.close()
    assert all(w.exitcode==0 for w in processes)
    save(HERE/"responses.json.gz",log)
    save(HERE/"receipt.json",{"worker_pids":pids,"parent":os.getpid(),"wire_order":sha(lockfile),
         "responses":sha(HERE/"responses.json.gz"),"actual":len(log),"distinct":len(ref)})
if __name__=="__main__":
    main()


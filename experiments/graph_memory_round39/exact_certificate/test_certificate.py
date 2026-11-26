"""Deterministic certificate and exhaustive oracle under source deletions in a frozen ordered pool."""
from itertools import combinations
from pathlib import Path
import hashlib
import json
import math
import random
import sqlite3
import struct
import sys
import numpy as np
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"packet_invalidation"))
from serve import Snapshot,DEMO,selection,picker

def bits(ix):
    value=0
    for i in ix:value|=1<<int(i)
    return value

def unchanged(deleted,old_packet,old_barrier,rows,cap):
    if deleted&old_packet:return False
    if not deleted&old_barrier:return True
    spent=0
    for i,c,_ in rows:
        bit=1<<i
        if deleted&bit:continue
        if spent+c>cap//2:break
        if not bit&old_packet:return False
        spent+=c
    return True

def brute(rows,cap,excluded):
    pool=[r for r in rows if not excluded&(1<<r[0])]
    protected=0;price=0
    for i,c,_ in pool:
        if price+c>cap//2:break
        protected|=1<<i;price+=c
    feasible=bits(r[0] for r in pool);best=None
    for m in range(1<<len(rows)):
        if m&~feasible or protected&~m:continue
        if sum(c for i,c,_ in rows if m&(1<<i))>cap:continue
        val=sum(u for i,_,u in rows if m&(1<<i));key=(val,-m)
        if best is None or key>best[0]:best=(key,m)
    return best[1]

def synthetic(solve):
    rng=random.Random(39032);total=pos=ties=0
    for _ in range(320):
        n=rng.randrange(1,9);cap=rng.randrange(1,18)
        rows=[(i,rng.randrange(1,10),rng.randrange(1,4)) for i in range(n)]
        base,barrier=selection(rows,cap,solve);old=bits(base);b=0 if barrier is None else 1<<barrier
        ties+=len({u for _,_,u in rows})<len(rows)
        assert brute(rows,cap,0)==old
        for z in range(1<<n):
            yes=unchanged(z,old,b,rows,cap);truth=brute(rows,cap,z)
            dp,_=selection([r for r in rows if not z&(1<<r[0])],cap,solve)
            assert bits(dp)==truth and yes==(old==truth)
            total+=1;pos+=yes
    return dict(pools=320,pools_with_repeated_utilities=ties,all_subsets=total,unchanged=pos)

def design():
    db=Snapshot(DEMO/"reader.sqlite");qs=db.queries() if hasattr(db,"queries") else [x[0] for x in db.conn.execute("SELECT q FROM query ORDER BY q")]
    design={}
    for q in qs:
        src=[s[0] for s in db.conn.execute("SELECT DISTINCT source FROM span WHERE q=? ORDER BY source",(q,))]
        n=len(src);rng=random.Random(int.from_bytes(hashlib.sha256(("fixed-compound|"+q).encode()).digest()[:8],"big"))
        regs={}
        for k in (1,2,3,8):
            total=math.comb(n,k) if n>=k else 0
            if k in (1,2) or total<=100:sets=list(combinations(range(n),k))
            else:
                selected=set()
                while len(selected)<100:selected.add(tuple(sorted(rng.sample(range(n),k))))
                sets=sorted(selected)
            regs[str(k)]=sets
        design[q]=dict(sources=src,sets=regs)
    picker.save(D/"schedule.json.gz",design)
    picker.save(D/"seal.json",dict(plan=picker.sha(D/"PROTOCOL_RU.md"),schedule=picker.sha(D/"schedule.json.gz"),projection=picker.sha(DEMO/"reader.sqlite"),code=picker.sha(D/"test_certificate.py")))
    return design

def run():
    plan=design();db=Snapshot(DEMO/"reader.sqlite");small=synthetic(db.solve)
    records={};counts={k:dict(treatments=0,unchanged=0,false_hit_selected=0,avoidable_barrier_recompute=0,extra_prefix_checks=0,false_positive=0,false_negative=0) for k in ("1","2","3","8")}
    ref=json.loads((DEMO/"reference.json").read_bytes());first=picker.read(D.parent/"packet_invalidation/observations.json.gz")
    for q,p in plan.items():
        rows=db.rows(q,None);cached,barrier=selection(rows,2048,db.solve);assert list(cached)==ref[q]["ids"]
        old=bits(cached);b=0 if barrier is None else 1<<barrier
        adj={v:0 for v in p["sources"]}
        for i,s in db.conn.execute("SELECT DISTINCT id,source FROM span WHERE q=?",(q,)):
            adj[s]|=1<<i
        src=[adj[v] for v in p["sources"]];records[q]={}
        single={r["source"]:r["full_packet"] for r in first[q]["rows"]}
        for k,sets in p["sets"].items():
            vals=[];cnt=counts[k]
            for us in sets:
                z=0
                for j in us:z|=src[j]
                valid=unchanged(z,old,b,rows,2048);weak=not bool(z&old);fast=not bool(z&(old|b))
                rem=[row for row in rows if not z&(1<<row[0])]
                full,_=selection(rem,2048,db.solve);actual=full==cached
                cnt["treatments"]+=1;cnt["unchanged"]+=actual;cnt["false_hit_selected"]+=int(weak and not actual)
                cnt["avoidable_barrier_recompute"]+=int(actual and not fast);cnt["extra_prefix_checks"]+=int(weak and not fast)
                cnt["false_positive"]+=int(valid and not actual);cnt["false_negative"]+=int(not valid and actual)
                assert valid==actual and (not fast or actual)
                if k=="1":assert list(full)==single[p["sources"][us[0]]]
                packed=struct.pack("<"+"I"*len(full),*full)
                vals.append([int(weak),int(fast),int(valid),int(actual),hashlib.sha256(packed).hexdigest()])
            records[q][k]=vals
    picker.save(D/"outcomes.json.gz",records);picker.save(D/"results.json",dict(counts=counts,synthetic=small,queries=len(plan),outcomes=picker.sha(D/"outcomes.json.gz"),seal=picker.sha(D/"seal.json")))
    print(counts,small,flush=True)
if __name__=="__main__":run()


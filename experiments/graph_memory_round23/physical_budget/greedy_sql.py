"""Exact cached greedy packing with priority updates and interval conflicts."""
from collections import defaultdict
import bisect
import hashlib
import json
import sqlite3

BUDGETS=(1024,1536,2048,3072)
CASES=("random1","selected1","random8","random32","all","insert1")
PROJECTION="neg,j,c,e,l,h"
INDEX="SELECT "+PROJECTION+" FROM blocks INDEXED BY idx_priority WHERE q=? ORDER BY neg,j"
SCAN="SELECT "+PROJECTION+" FROM blocks INDEXED BY sqlite_autoindex_blocks_1 WHERE q=? ORDER BY neg,j"
SUFFIX="SELECT "+PROJECTION+" FROM blocks INDEXED BY idx_priority WHERE q=? AND (neg,j)>=(?,?) ORDER BY neg,j"

def key(x):return (x[0],x[1])
def row(x,alt=False):
    j,a,b,c,e,l,h=x
    return (-(b if alt else a),j,c,e,l,h)

def allowed(used,e,l,h):
    return all(h<=a or b<=l for a,b in used[e])

def state(core,budget,prefix):
    spans=defaultdict(list);left=budget
    for _,c,e,l,h in core:
        left-=c;spans[e].append((l,h))
    for _,j,c,e,l,h in prefix:
        left-=c;assert left>=0 and allowed(spans,e,l,h)
        spans[e].append((l,h))
    assert left>=0
    return spans,left

def consume(rows,core,budget,prefix=()):
    chosen=list(prefix);used,left=state(core,budget,prefix);reads=0
    if left:
        for rec in rows:
            reads+=1;neg,j,c,e,l,h=rec
            if c<=left and allowed(used,e,l,h):
                used[e].append((l,h));chosen.append(rec);left-=c
                if not left:break
    return chosen,reads

def greedy(items,core,budget):
    # Independent slow reference, rescans selected intervals without cursor or index.
    free=budget-sum(v[1] for v in core)
    occupied=[(r[2],r[3],r[4]) for r in core];out=[]
    for rec in sorted(items,key=key):
        _,j,c,e,l,h=rec
        if c<=free and all(e!=ev or h<=start or end<=l for ev,start,end in occupied):
            out.append(rec);occupied.append((e,l,h));free-=c
    return out

def changes(items,old_picks,case,q,budget):
    by={x[0]:x for x in items}
    order=lambda j:hashlib.sha256(f"pack-update/change/{q}/{j}".encode()).digest()
    if case=="insert1":
        j=min(by,key=order);return [(None,row(by[j]))]
    possible={j for j,v in by.items() if v[1]!=v[2]}
    if case=="selected1":possible&={r[1] for r in old_picks}
    n={"random1":1,"selected1":1,"random8":8,"random32":32,"all":len(possible)}[case]
    return [(row(by[j]),row(by[j],True)) for j in sorted(possible,key=order)[:n]]

def persist(c,q,budget,old,new):
    if old==new:return 0
    body=json.dumps(new,separators=(",",":")).encode()
    c.execute("update answers set body=? where q=? and budget=?",(body,q,budget))
    return len(body)

def cached(c,q,budget):
    body=c.execute("select body from answers where q=? and budget=?",(q,budget)).fetchone()[0]
    return [tuple(r) for r in json.loads(body)],len(body)

def write(c,q,mutation):
    updates=[(new[0],q,new[1]) for old,new in mutation if old is not None]
    adds=[(q,new[1],new[0],*new[2:]) for old,new in mutation if old is None]
    if updates:c.executemany("update blocks set neg=? where q=? and j=?",updates)
    if adds:c.executemany("insert into blocks(q,j,neg,c,e,l,h) values(?,?,?,?,?,?,?)",adds)

def rebuild(c,q,core,budget,sql=INDEX):
    cursor=c.execute(sql,(q,))
    try:return consume(cursor,core,budget)
    finally:cursor.close()

def repair(c,q,core,budget,old,mutation):
    if not mutation:return old,0,"unchanged"
    if len(mutation)>32:
        picked,reads=rebuild(c,q,core,budget)
        return picked,reads,"full"
    selected={r[1] for r in old}
    newrows=sorted((v for _,v in mutation),key=key)
    if all(prev is None or prev[1] not in selected for prev,_ in mutation):
        # If every changed candidate is rejected by the old earlier choices, induction
        # preserves all subsequent choices, including interactions between changed rows.
        used,free=state(core,budget,());i=0
        for new in newrows:
            while i<len(old) and key(old[i])<key(new):
                _,_,cost,e,l,h=old[i];free-=cost;used[e].append((l,h));i+=1
            _,j,cost,e,l,h=new
            if cost<=free and allowed(used,e,l,h):break
        else:return old,0,"certified"
    boundary=min(key(rec) for pr in mutation for rec in pr if rec is not None)
    n=bisect.bisect_left([key(r) for r in old],boundary)
    cursor=c.execute(SUFFIX,(q,*boundary))
    try:
        picked,reads=consume(cursor,core,budget,old[:n])
        return picked,reads,"suffix"
    finally:cursor.close()


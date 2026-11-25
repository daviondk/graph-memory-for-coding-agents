"""Compare exact multi-retraction policies at the same input boundary on actual SQLite files."""
from functools import lru_cache
from pathlib import Path
from time import perf_counter_ns as now
import random
import sqlite3
import zlib
import numpy as np
from multiban_design import D,MODES,read,save,sha,pack,merge,decode,arrays
from store import state,open_all
from control import geometry,better

fields="score,ord,lo,hi"
@lru_cache(maxsize=50)
def rank_sql(table,n):
    terms="".join(" AND (hi<=? OR lo>=?)" for _ in range(n))
    return f"SELECT {fields} FROM {table}.r WHERE q=?"+terms+" ORDER BY score DESC,ord LIMIT 1"

def flattened(bans):
    return tuple(x for b in bans for x in b)

def complement(bans):
    g=[];left=-2147483648
    for a,b in bans:
        if left<a:g.append((left,a))
        left=b
    if left<2147483647:g.append((left,2147483647))
    return g

def range_lookup(db,ix,bans):
    parts=complement(bans)
    values=",".join("(?,?)" for _ in parts)
    query="WITH f(l,h) AS (VALUES "+values+") SELECT l,(SELECT i FROM rng.coord WHERE q=? AND endpoint<=h ORDER BY endpoint DESC LIMIT 1) FROM f"
    pair=db.execute(query,(*flattened(parts),ix)).fetchall()
    buckets=[]
    for left,n in pair:
        while n:
            buckets.append((n,left));n-=n&-n
    if not buckets:return None,[1,0,0,0,0,0,len(pair),0]
    sql="""WITH s(b,g) AS (VALUES """+",".join("(?,?)" for _ in buckets)+""")
      SELECT v.score,v.ord,v.lo,v.hi FROM s CROSS JOIN rng.cell AS v
      WHERE v.q=? AND v.bucket=s.b AND v.threshold=(
        SELECT e.threshold FROM rng.cell AS e WHERE e.q=? AND e.bucket=s.b AND e.threshold>=s.g ORDER BY e.threshold LIMIT 1
      ) ORDER BY v.score DESC,v.ord LIMIT 1"""
    best=db.execute(sql,(*flattened(buckets),ix,ix)).fetchone()
    return best,[2,0,0,0,0,len(buckets),len(pair),0]

def scan_window(blob,w,bans):
    a,b,seg,lo,hi=decode(zlib.decompress(blob))
    if not len(a):return None
    geom,ends=geometry(len(a));valid=geom & (seg[:,None]>=0)&(seg[:,None]==seg[ends])
    for l,h in bans:valid &= (hi[ends]<=l)|(lo[:,None]>=h)
    score=np.where(valid,a[:,None]+b[ends],np.float32(-np.inf));i,delta=divmod(int(np.argmax(score)),30)
    if np.isneginf(score[i,delta]):return None
    return float(score[i,delta]),(w*384+i)*30+delta,int(lo[i]),int(hi[i+delta])

def lookup(db,m,ix,bans):
    if m=="range2d":return range_lookup(db,ix,bans)
    table={"full":"main","pareto":"pareto","top64":"top64"}[m]
    row=db.execute(rank_sql(table,len(bans)),(ix,*flattened(bans))).fetchone()
    calls=1;transferred=0;windows=0;bounds=0
    if row or m!="top64":return row,[calls,0,0,0,0,0,0,0]
    calls+=1;found=None
    for s,o,l,h,w in db.execute("SELECT score,ord,lo,hi,w FROM bounds.r WHERE q=? ORDER BY score DESC,ord",(ix,)):
        bounds+=1;upper=(s,o,l,h)
        if not better(upper,found):break
        if all(h<=a or l>=b for a,b in bans):candidate=upper
        else:
            buf=db.execute("SELECT b FROM zip.r WHERE q=? AND w=?",(ix,w)).fetchone()[0]
            transferred+=len(buf);windows+=1;calls+=1;candidate=scan_window(buf,w,bans)
        if better(candidate,found):found=candidate
    return found,[calls,transferred,windows,bounds,1,0,0,0]

def independent(ws):
    s=[];o=[];l=[];h=[]
    for w,(a,b,seg,lo,hi) in enumerate(ws):
        n=len(a)
        for dist in range(min(30,n)):
            inds=np.flatnonzero((seg[:n-dist]>=0)&(seg[:n-dist]==seg[dist:]))
            j=inds+dist;s.append(a[inds]+b[j]);o.append((w*384+inds)*30+dist);l.append(lo[inds]);h.append(hi[j])
    score,order,lo,hi=map(np.concatenate,(s,o,l,h));perm=np.lexsort((order,-score))
    return score[perm],order[perm],lo[perm],hi[perm]

def oracle(tab,bans):
    score,order,lo,hi=tab
    good=np.ones(len(order),dtype=bool)
    for a,b in bans:good &= (hi<=a)|(lo>=b)
    good=np.flatnonzero(good)
    if not len(good):return None,len(order)
    i=good[0];return (float(score[i]),int(order[i]),int(lo[i]),int(hi[i])),int(i)+1

def as_queries(groups,tab):
    lo=tab[2];hi=tab[3];left=int(np.min(lo));right=int(np.max(hi))
    k=int(np.argmin(hi-lo));l=int(lo[k]);h=int(hi[k])
    extra={"all":[(left-1,right+1)],"none":[],"interior":[(left-2,l),(h,right+2)]}
    regular={f"{kind}-{k}":merge(xs) for kind in ("independent","targeted") for k,xs in groups[kind].items()}
    return {**regular,**extra}

def main():
    p,cases,old,logs,base=state();db=open_all(old,logs,base);db.execute("PRAGMA query_only=1");db.execute("BEGIN")
    f=read(D/"scenarios.json.gz");storage=read(D/"build-seal.json")
    raw=sqlite3.connect(logs/"raw.sqlite");result={};work=[];checked=0
    for ix,q in enumerate(p["qids"]):
        ws=[decode(x[0]) for x in raw.execute("SELECT b FROM r WHERE q=? ORDER BY w",(ix,))]
        tab=independent(ws)
        # SQLite compact layout is independently read back to establish its logical scan depth.
        pr=db.execute("SELECT score,ord,lo,hi FROM pareto.r WHERE q=? ORDER BY score DESC,ord",(ix,)).fetchall()
        pt=tuple(np.asarray(x) for x in zip(*pr))
        result[q]={}
        for cond,bans in as_queries(f[q],tab).items():
            expected,fulln=oracle(tab,bans);other,pn=oracle(pt,bans);assert pack(other)==pack(expected)
            costs={}
            for m in MODES:
                found,cost=lookup(db,m,ix,bans);assert pack(found)==pack(expected),(m,q,cond,expected,found,bans)
                cost[-1]=fulln if m=="full" else pn if m=="pareto" else 0
                costs[m]=cost;checked+=1
            result[q][cond]={"ban":bans,"answer":expected,"costs":costs}
            if "-" in cond and q in p["panel"]:work.append((q,ix,cond,bans))
        if (ix+1)%16==0:print("validated",ix+1,flush=True)
    for _,ix,_,bans in work:
        for m in MODES:lookup(db,m,ix,bans)
    rng=random.Random(29314);timing=[]
    for rep in range(15):
        seq=work.copy();rng.shuffle(seq)
        for q,ix,cond,bans in seq:
            methods=list(MODES);rng.shuffle(methods)
            for m in methods:
                t=now();found,cost=lookup(db,m,ix,bans);out=pack(found);ns=now()-t
                timing.append([q,cond,m,rep,ns])
    db.execute("COMMIT");db.close();raw.close()
    save(D/"predictions.json.gz",result);save(D/"latency.json.gz",timing)
    save(D/"measurement-seal.json",{"plan":sha(D/"plan.json"),"store":sha(D/"build-seal.json"),"scenarios":sha(D/"scenario-seal.json"),
         "code":sha(Path(__file__)),"predictions":sha(D/"predictions.json.gz"),"latency":sha(D/"latency.json.gz"),
         "strict":checked,"timings":len(timing),"cost_fields":["sql_calls","blob_bytes","recomputed_windows","bound_rows","fallback","fenwick_cells","coordinate_rows","logical_score_rows"]})
if __name__=="__main__":main()

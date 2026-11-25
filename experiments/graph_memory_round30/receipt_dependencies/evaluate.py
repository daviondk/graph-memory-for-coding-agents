"""Evaluate true exact receipt, partial and mixed updates and warm on-disk lookup time."""
from pathlib import Path
from time import perf_counter_ns as now
from functools import lru_cache
import random
import sqlite3
import numpy as np
from inputs import D,R,read,save,sha,merge,pack,decode
from build import sources
from measure import scan_window,better,independent,oracle

@lru_cache(None)
def lookup_sql(known,n):
    cond="(r.mask & ?) = 0" if known else "1"+"".join(" AND (r.hi<=? OR r.lo>=?)" for _ in range(n))
    return """SELECT c.full_mask,c.first_omitted_rank,c.geometric_limit,x.rank,x.score,x.ord,x.lo,x.hi
      FROM cert c LEFT JOIN r x ON x.q=c.q AND x.rank=(SELECT r.rank FROM r
      WHERE r.q=c.q AND """+cond+" ORDER BY r.rank LIMIT 1) WHERE c.q=?"

def cached(db,ix,known,bits,bans):
    args=(bits,ix) if known else tuple(v for b in bans for v in b)+(ix,)
    complete,cut,glim,rank,s,o,l,h=db.execute(lookup_sql(known,len(bans)),args).fetchone()
    val=None if rank is None else (s,o,l,h)
    if known:cert=bool(complete or (rank is not None and rank<cut))
    else:cert=bool(rank is not None and rank<glim)
    return val,cert

def ask(db,ix,known,bits,bans):
    found,cert=cached(db,ix,known,bits,bans);present=found
    calls=1;windows=0;traffic=0
    if not cert:
        calls+=1
        for s,o,l,h,w in db.execute("SELECT score,ord,lo,hi,w FROM bounds.r WHERE q=? ORDER BY score DESC,ord",(ix,)):
            upper=(s,o,l,h)
            if not better(upper,found):break
            if all(h<=a or l>=b for a,b in bans):v=upper
            else:
                blob=db.execute("SELECT b FROM z.r WHERE q=? AND w=?",(ix,w)).fetchone()[0]
                traffic+=len(blob);windows+=1;calls+=1;v=scan_window(blob,w,bans)
            if better(v,found):found=v
    return found,present,cert,windows,traffic,calls

def run():
    p,cases,old,logs,base,dest=sources();plan=read(D/"plan.json");ev=read(D/"events.json.gz")
    connections={}
    for m in plan["policies"]:
        for k in (8,64):
            name=m+str(k);db=sqlite3.connect(dest/(name+".sqlite"));db.execute("ATTACH DATABASE ? AS bounds",(str(logs/"bounds.sqlite"),))
            db.execute("ATTACH DATABASE ? AS z",(str(logs/"zip.sqlite"),));db.execute("PRAGMA query_only=1");db.execute("BEGIN");connections[name]=db
    raw=sqlite3.connect(logs/"raw.sqlite");regdb=sqlite3.connect(dest/"registry.sqlite")
    answers={};times=[];timed=[];strict=0
    for ix,q in enumerate(p["qids"]):
        v=ev[q];reg=[(l,h) for l,h in regdb.execute("SELECT lo,hi FROM r WHERE q=? ORDER BY i",(ix,))]
        assert [list(x) for x in reg]==v["registry"]
        orig=independent([decode(b) for b, in raw.execute("SELECT b FROM r WHERE q=? ORDER BY w",(ix,))])
        sequences=[(grp,name,ids,[]) for grp in ("primary","sampled") for name,ids in v[grp].items()]
        sequences += [("outside",name,data["known"],data["unknown"]) for name,data in v["outside"].items()]
        answers[q]={}
        for group,cond,known,unknown in sequences:
            bits=sum(1<<j for j in known);bans=merge([reg[j] for j in known]+[tuple(z) for z in unknown]);gold,_=oracle(orig,bans)
            entry={"gold":gold,"arms":{}}
            for arm,db in connections.items():
                found,present,cert,nwin,traffic,calls=ask(db,ix,not unknown,bits,bans)
                assert pack(found)==pack(gold),(q,group,cond,arm,found,gold)
                optimistic=int(present is not None and pack(present)==pack(gold))
                ignore_error=None
                if unknown:
                    guessed,_=cached(db,ix,True,bits,bans)
                    ignore_error=int(pack(guessed)!=pack(gold))
                entry["arms"][arm]=[int(cert),int(cert and gold is None),optimistic,nwin,traffic,calls,ignore_error]
                strict+=1
            answers[q][group+"/"+cond]=entry
            if group=="primary" and q in p["panel"]:timed.append((q,ix,cond,bits,bans))
        if (ix+1)%8==0:print("validated",ix+1,flush=True)
    names=[k for k in connections if k.endswith("64")]
    for _,ix,_,bits,bans in timed:
        for n in names:ask(connections[n],ix,True,bits,bans)
    rng=random.Random(30051)
    for repeat in range(12):
        seq=timed.copy();rng.shuffle(seq)
        for q,ix,c,bits,bans in seq:
            methods=names.copy();rng.shuffle(methods)
            for n in methods:
                t=now();v,_,_,_,_,_=ask(connections[n],ix,True,bits,bans);payload=pack(v);ns=now()-t
                times.append([q,c,n,repeat,ns])
    for db in connections.values():db.execute("COMMIT");db.close()
    raw.close();regdb.close()
    save(D/"answers.json.gz",answers);save(D/"latency.json.gz",times)
    save(D/"result-seal.json",{"code":sha(Path(__file__)),"input":sha(D/"event-seal.json"),"build":sha(D/"build-seal.json"),"answers":sha(D/"answers.json.gz"),
         "timings":sha(D/"latency.json.gz"),"strict":strict,"latency_samples":len(times),"fields":["certified","certified_null","correct_candidate_present","windows","blob_bytes","sql_calls","naive_ignore_unknown_wrong"]})
if __name__=="__main__":run()

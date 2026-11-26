"""Paired warm query microbenchmark over actual changing SQLite relations."""
import argparse
from collections import Counter,defaultdict
from hashlib import sha256
from heapq import nlargest
from pathlib import Path
import random
import sqlite3
from statistics import median
import struct
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from retain import HERE,Retained
sys.path.insert(0,str(HERE.parent/"event_intersection"))
from event_bounds import EpisodeState
from evaluate import panels,chosen
from run import save,load

METHODS=("sql_group","packed","pair_table","bitset","suffix25","own_archive","shared_archive")
SCRATCH=Path("D:/CodexResearch/x20-r56-event-history")
SCHEMA="""
CREATE TABLE post(f INTEGER,j INTEGER,PRIMARY KEY(f,j)) WITHOUT ROWID;
CREATE INDEX members ON post(j,f);
CREATE TABLE ev(j INTEGER PRIMARY KEY,buf BLOB NOT NULL);
CREATE TABLE cold_post(f INTEGER,j INTEGER,PRIMARY KEY(f,j)) WITHOUT ROWID;
CREATE TABLE cold_ev(j INTEGER PRIMARY KEY,buf BLOB NOT NULL);
CREATE TABLE pair(a INTEGER,b INTEGER,n INTEGER,PRIMARY KEY(a,b)) WITHOUT ROWID;
"""
READ="SELECT e.buf FROM post p JOIN ev e ON e.j=p.j WHERE p.f=?"
COLD="SELECT e.buf FROM cold_post p JOIN cold_ev e ON e.j=p.j WHERE p.f=?"
GROUP="SELECT b.f,COUNT(*) FROM post a JOIN post b ON b.j=a.j WHERE a.f=? AND b.f<>a.f GROUP BY b.f"
EXACT="SELECT COUNT(*) FROM post a CROSS JOIN post b WHERE a.f=? AND a.j<? AND b.f=? AND b.j=a.j"

def sparse(scores,anchor,freq,prior):
    ranked=nlargest(8,((n,freq[i],-i) for i,n in scores.items() if i!=anchor and n))
    keep={-key[2] for key in ranked}
    for i in prior:
        if len(ranked)>=8:break
        if i not in keep and i!=anchor:ranked.append((0,freq[i],-i))
    return [(-i,n) for n,_,i in ranked]

def measure(repo,rows,panel,db,storage):
    conn=sqlite3.connect(db)
    if storage=="wal":conn.execute("PRAGMA journal_mode=WAL").fetchone()
    conn.executescript(SCHEMA)
    all_events=EpisodeState(25)
    resident=Retained(8,"last",repo)
    ids={};window=[];freq=Counter()
    rng=random.Random(56031)
    records=[];writes=Counter()
    for t,(rev,raw) in enumerate(rows):
        paths=raw if len(raw)<=64 else []
        name=chosen(panel,rev,t,len(rows),paths)
        if name is not None:
            anchor=ids.get(name,-1)
            pool=[i for i in range(len(ids)) if i!=anchor]
            prior=nlargest(9,range(len(ids)),key=lambda i:(freq[i],-i))
            expected=sparse(Counter(i for j in all_events.all.get(anchor,()) for i in all_events.members[j]),anchor,freq,prior)
            def query(method):
                stats=[0,0,0]
                def fetch(sql,args):
                    stats[0]+=1
                    rr=conn.execute(sql,args).fetchall()
                    stats[1]+=len(rr)
                    return rr
                if method=="bitset":
                    bits=all_events.bitset.get(anchor,0)
                    weights={i:(bits&all_events.bitset.get(i,0)).bit_count() for i in pool}
                    return sparse(weights,anchor,freq,prior),stats
                if method=="suffix25":
                    def exact(a,b,cut,a_first):
                        x,y=(a,b) if a_first else (b,a)
                        return fetch(EXACT,(x,cut,y))[0][0]
                    return all_events.packet(anchor,pool,freq,"aligned",sql=exact)[0],stats
                if method in ("sql_group","pair_table"):
                    command=GROUP if method=="sql_group" else "SELECT b,n FROM pair WHERE a=?"
                    return sparse(dict(fetch(command,(anchor,))),anchor,freq,prior),stats
                if method=="packed":
                    hot=();remote=fetch(READ,(anchor,))
                elif method=="own_archive":
                    hot=[j for _,j in resident.owned.get(anchor,())]
                    remote=fetch(READ+" AND p.j<?",(anchor,min(hot))) if len(hot)<resident.total[anchor] else ()
                else:
                    hot=resident.incident.get(anchor,())
                    remote=fetch(COLD,(anchor,)) if len(hot)<resident.total[anchor] else ()
                counts=Counter()
                for j in hot:counts.update(resident.events[j])
                for (buf,) in remote:
                    stats[2]+=len(buf)
                    counts.update(struct.unpack("<"+"I"*(len(buf)//4),buf))
                return sparse(counts,anchor,freq,prior),stats
            clock=defaultdict(list);cost={}
            for _ in range(5):
                order=list(METHODS);rng.shuffle(order)
                for m in order:
                    start=perf_counter_ns()
                    rank,counts=query(m)
                    clock[m].append(perf_counter_ns()-start)
                    assert rank==expected,(m,repo,t,rank,expected)
                    assert cost.setdefault(m,counts)==counts
            records.append(dict(t=t,timing=clock,cost=cost))
        codes=[ids.setdefault(p,len(ids)) for p in paths]
        window.append(codes)
        if t>=32:freq.subtract(window[t-32])
        freq.update(codes)
        if len(codes)<2:continue
        # Archive exactly those events whose final owner is dropped by this commit.
        old_candidates={resident.owned[f][0][1] for f in codes if len(resident.owned.get(f,()))==8}
        j=len(all_events.members)
        all_events.observe(codes)
        resident.ingest(codes,paths,rev,j)
        def store(prefix,event,members):
            fmt="<"+"I"*len(members)
            conn.execute("INSERT INTO "+prefix+"ev VALUES(?,?)",(event,struct.pack(fmt,*members)))
            conn.executemany("INSERT INTO "+prefix+"post VALUES(?,?)",((f,event) for f in members))
            writes[prefix+"member_rows"]+=len(members)
            writes[prefix+"event_rows"]+=1
        store("",j,codes)
        for old in old_candidates:
            if old not in resident.events:store("cold_",old,all_events.members[old])
        conn.executemany("INSERT INTO pair VALUES(?,?,1) ON CONFLICT(a,b) DO UPDATE SET n=n+1",
                         ((a,b) for a in codes for b in codes if a!=b))
        writes["pair_updates"]+=len(codes)*(len(codes)-1)
        conn.commit()
    assert writes["cold_event_rows"]+len(resident.events)==writes["event_rows"]
    conn.close()
    return dict(writes=writes,queries=records)

def summarize(groups):
    records=[r for s in groups.values() for r in s["queries"]]
    out={}
    for m in METHODS:
        totals=[sum(r["timing"][m][i] for r in records)/1e6 for i in range(5)]
        out[m]=dict(median_ms=median(totals),totals_ms=totals,
                    sql=sum(r["cost"][m][0] for r in records),rows=sum(r["cost"][m][1] for r in records),
                    payload=sum(r["cost"][m][2] for r in records))
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument("mode",choices=["ram","wal","summarize"])
    args=ap.parse_args()
    if args.mode=="summarize":
        for mode in ("ram","wal"):
            d=load(HERE/("physical-"+mode+".json.gz"))
            assert {p:summarize(g) for p,g in d.items()}==load(HERE/("physical-"+mode+"-summary.json"))
        return
    data=panels();out={}
    SCRATCH.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=SCRATCH) as folder:
        for panel in ("B","long"):
            gs={}
            for i,(repo,rs) in enumerate(data[panel].items()):
                db=":memory:" if args.mode=="ram" else str(Path(folder)/(panel+str(i)+".sqlite"))
                gs[repo]=measure(repo,rs,panel,db,args.mode)
            out[panel]=gs
            print(panel,{k:round(v["median_ms"],2) for k,v in summarize(gs).items()},flush=True)
    save(HERE/("physical-"+args.mode+".json.gz"),out)
    save(HERE/("physical-"+args.mode+"-summary.json"),{p:summarize(g) for p,g in out.items()})
if __name__=="__main__":main()

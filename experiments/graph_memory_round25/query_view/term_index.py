"""Hydrate only query postings; compare a compressed state blob with a real term-addressable B-tree."""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import hashlib
import random
import sqlite3
import numpy as np
from hydrate import FILE,interpret,D,DB,PRIVATE,decode,pack,read,write,sha,bag,select

INDEX = PRIVATE/"terms.sqlite"

def varint(n):
    result=bytearray()
    while n>=128:
        result.append((n&127)|128);n>>=7
    result.append(n)
    return result

def encode(entries):
    out=bytearray();last=-1
    for idx,f in sorted(entries):
        out.extend(varint(idx-last));out.extend(varint(f));last=idx
    return bytes(out)

def expand(blob):
    numbers=[];n=shift=0
    for b in blob:
        n|=(b&127)<<shift
        if b&128:shift+=7
        else:numbers.append(n);n=shift=0
    assert shift==0 and len(numbers)%2==0
    out={};last=-1
    for gap,f in zip(numbers[::2],numbers[1::2]):
        last+=gap;out[last]=f
    return out

def build(src):
    with TemporaryDirectory(dir=PRIVATE) as tmp:
        stage=Path(tmp)/"new.sqlite";con=sqlite3.connect(stage)
        con.executescript("""
        CREATE TABLE snapshots(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,header BLOB NOT NULL);
        CREATE TABLE terms(id INTEGER NOT NULL,term TEXT NOT NULL,postings BLOB NOT NULL,PRIMARY KEY(id,term)) WITHOUT ROWID;
        """)
        for i,(sid,vraw,iraw) in enumerate(src.execute("select sid,projected,inverted from snapshot order by sid"),1):
            rows=decode(vraw)["rows"];header=pack([[r["coords"] for r in rows],[r["length"] for r in rows]])
            con.execute("insert into snapshots values(?,?,?)",(i,sid,header))
            posted=[]
            for term,group in decode(iraw).items():
                truth={int(k):f for k,f in group.items()}
                packed=encode(truth.items());assert expand(packed)==truth
                posted.append((i,term,packed))
            con.executemany("insert into terms values(?,?,?)",posted)
        con.commit();con.execute("vacuum");assert con.execute("pragma integrity_check").fetchone()==("ok",)
        query_plan=con.execute("explain query plan select term,postings from terms where id=? and term in (?,?)",(1,"alpha","beta")).fetchall()
        rowcounts=dict(snapshots=con.execute("select count(*) from snapshots").fetchone()[0],posting_rows=con.execute("select count(*) from terms").fetchone()[0])
        con.close()
        if INDEX.exists():assert sha(INDEX)==sha(stage)
        else:stage.replace(INDEX)
    return query_plan,rowcounts

def header_view(coords,lens):
    return {"rows":[{"coords":coord,"length":n} for coord,n in zip(coords,lens)]}

def readonly(path):
    return sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)

def main():
    src=readonly(DB);plans,counts=build(src)
    layouts=readonly(FILE);btree=readonly(INDEX)
    ref={(r["g"],r["q"]):r for r in read(D/"decisions.json.gz")}
    obs=[]
    variants=("inverted_all","inverted_terms_only","term_btree","bloom_lazy")
    for sid,q,query in src.execute("select sid,q,question from future order by sid,q"):
        reference=ref[sid,q];rng=random.Random(hashlib.sha256(("sql-postings/"+q).encode()).digest())
        rep_count=4 if int.from_bytes(hashlib.sha256(("load-repeat/"+q).encode()).digest()[:2],"little")%8==0 else 1
        for rep in range(rep_count):
            order=list(variants);rng.shuffle(order)
            for variant in order:
                size=0;source_bytes=0;source_rows=0;rows_returned=0
                def fetch(i):
                    nonlocal source_bytes,source_rows
                    (raw,)=src.execute("select body from payload where sid=? and idx=?",(sid,i)).fetchone()
                    source_bytes+=len(raw);source_rows+=1
                    return bag(raw.decode())
                start=perf_counter_ns()
                if variant=="term_btree":
                    words=sorted(bag(query))
                    idx,head=btree.execute("select id,header from snapshots where name=?",(sid,)).fetchone()
                    coords,lens=decode(head);view=header_view(coords,lens);size=len(head);rows_returned=1
                    sql="select term,postings from terms where id=? and term in ("+",".join("?" for _ in words)+")"
                    inv={}
                    if words:
                        for term,blob in btree.execute(sql,(idx,*words)):
                            inv[term]=expand(blob);size+=len(term.encode())+len(blob);rows_returned+=1
                    result=select(view,query,"inverted",fetch,inv)
                else:
                    stored="bloom_lazy" if variant=="bloom_lazy" else "inverted"
                    (blob,)=layouts.execute("select data from data where sid=? and method=?",(sid,stored)).fetchone()
                    size=len(blob);rows_returned=1
                    data=decode(blob)
                    if variant=="inverted_terms_only":
                        coords,lens,lists=data;view=header_view(coords,lens)
                        inv={w:dict(lists[w]) for w in bag(query) if w in lists}
                    else:view,inv=interpret(data,stored)
                    result=select(view,query,stored,fetch,inv)
                ns=perf_counter_ns()-start
                assert result==reference["ref"]
                obs.append([reference["c"],sid,q,variant,rep,ns,size+source_bytes,rows_returned+source_rows])
    for conn in (btree,layouts,src):conn.close()
    out={}
    for co in ("isetrace","squad"):
        out[co]={}
        for v in variants:
            picks=[z for z in obs if z[0]==co and z[3]==v and z[4]==0]
            out[co][v]={"n":len(picks),"p50_us":np.median([z[5] for z in picks])/1000,
                "p95_us":np.quantile([z[5] for z in picks],.95)/1000,"mean_sql_bytes":np.mean([z[6] for z in picks]),
                "mean_rows":np.mean([z[7] for z in picks])}
    write(D/"postings-times.json.gz",obs)
    write(D/"postings-results.json",{"results":out,"size_bytes":INDEX.stat().st_size,"database_sha":sha(INDEX),
        "plan":plans,"counts":counts,"logged":len(obs),"receipt":sha(D/"postings-times.json.gz"),"protocol":sha(D/"POSTINGS_CONTROL_RU.md")})
    print(out)
if __name__=="__main__":main()

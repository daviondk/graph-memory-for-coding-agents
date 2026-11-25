"""Benchmark real SQLite fetches and validate the winning window against the original scorer."""
from collections import Counter,defaultdict
import hashlib
import random
import sqlite3
from time import perf_counter_ns
from make_fixture import DB,D,read,write,sha,decode
from ranking import bag,select
from novelty import Window,lexical_order

METHODS=("scan","df_scan","projected","exact_lazy","bloom_scan","bloom_lazy","bloom_cold","inverted")

def main():
    lock=read(D/"input-lock.json")
    assert sha(DB)==lock["private_sqlite"] and sha(D/"ranking.py")==lock["methods"] and sha(D/"make_fixture.py")==lock["writer"]
    assert sha(D/"PROTOCOL_RU.md")==lock["protocol"]
    conn=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    conn.execute("pragma query_only=1")
    out=[];times=[]
    for sid,corpus,group,q0,view_blob,invert_blob,size_blob,source_bytes in conn.execute("select * from snapshot order by sid"):
        view=decode(view_blob);inverted={s:{int(i):n for i,n in p.items()} for s,p in decode(invert_blob).items()}
        rows=view["rows"]
        original=[]
        for i,body in conn.execute("select idx,body from payload where sid=? order by idx",(sid,)):
            e,l,h,edge,eligible=rows[i]["coords"]
            original.append(Window(e,l,h,body.decode(),0))
        costs=decode(size_blob)
        for q,query in conn.execute("select q,question from future where sid=? order by q",(sid,)):
            ref=next((i for i in lexical_order(query,original) if rows[i]["coords"][4]),None)
            records={}
            rng=random.Random(int.from_bytes(hashlib.sha256(q.encode()).digest()[:8],"little"))
            repetitions=3 if int.from_bytes(hashlib.sha256(("timing/"+q).encode()).digest()[:2],"little")%8==0 else 1
            for rep in range(repetitions):
                order=list(METHODS);rng.shuffle(order)
                for method in order:
                    fetched=0;amount=0
                    def get(i):
                        nonlocal fetched,amount
                        (raw,)=conn.execute("select body from payload where sid=? and idx=?",(sid,i)).fetchone()
                        fetched+=1;amount+=len(raw)
                        return bag(raw.decode())
                    start=perf_counter_ns();winner=select(view,query,method,get,inverted);ns=perf_counter_ns()-start
                    if method!="projected":assert winner==ref,(corpus,q,method,winner,ref)
                    address=(None if winner is None else [rows[winner]["coords"][0],rows[winner]["coords"][3]])
                    v=[winner,address,fetched,amount]
                    if rep:assert records[method]==v
                    else:records[method]=v
                    times.append([corpus,sid,q,rep,method,ns])
            out.append({"c":corpus,"g":sid,"q":q,"ref":ref,"arms":records,"source_bytes":source_bytes,"size":costs})
    conn.close()
    write(D/"decisions.json.gz",out);write(D/"times.json.gz",times)
    write(D/"query-lock.json",{"inputs":sha(D/"input-lock.json"),"code":sha(D/"evaluate.py"),"decisions":sha(D/"decisions.json.gz"),
       "times":sha(D/"times.json.gz"),"queries":len(out),"timings":len(times)})
    print(len(out),len(times))
if __name__=="__main__":main()

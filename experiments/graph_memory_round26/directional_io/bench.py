"""Counterbalanced warm and fresh-connection reads. Verify every raw result after timing."""
from collections import defaultdict
import os,platform,random,sqlite3,sys
from time import perf_counter_ns
from cfg import *
METHODS=("text_pair","text_twice","text_right","text_half_right","whole_char","whole_byte","blob_pair","blob_twice","blob_translated")
URI=DB.as_uri()+"?mode=ro&immutable=1"
ONE="select substr(body,?,?) from field where rid=?"
TWO="select substr(body,?,?),substr(body,?,?) from field where rid=?"
WHOLE="select body from field where rid=?"
CHECK="select b from checkpoint where rid=? and c=?"
def connect():
    con=sqlite3.connect(URI,uri=True,cached_statements=128)
    con.text_factory=bytes;con.execute("pragma mmap_size=0");con.execute("pragma cache_size=-8192")
    return con
def fetch(con,r,method):
    rid=r["rid"];a,b=r["both"];right=r["right"];headers=0
    def one(s):return con.execute(ONE,(s["l"]+1,s["h"]-s["l"],rid)).fetchone()[0]
    def blob():return con.blobopen("field","body",rid,readonly=True)
    def readrange(f,s):
        f.seek(s["b"]);return f.read(s["z"]-s["b"])
    if method=="text_pair":
        out=con.execute(TWO,(a["l"]+1,a["h"]-a["l"],b["l"]+1,b["h"]-b["l"],rid)).fetchone();sql=1
    elif method=="text_twice":out=(one(a),one(b));sql=2
    elif method=="text_right":out=(one(right),);sql=1
    elif method=="text_half_right":out=(one(b),);sql=1
    elif method in ("whole_char","whole_byte"):
        body=con.execute(WHOLE,(rid,)).fetchone()[0]
        if method=="whole_char":
            txt=body.decode("utf8");out=tuple(txt[s["l"]:s["h"]].encode() for s in (a,b))
        else:out=(body[a["b"]:a["z"]],body[b["b"]:b["z"]])
        return out,len(body),1,0
    elif method=="blob_pair":
        with blob() as f:out=(readrange(f,a),readrange(f,b))
        return out,sum(map(len,out)),0,1
    elif method=="blob_twice":
        with blob() as f:l=readrange(f,a)
        with blob() as f:u=readrange(f,b)
        return (l,u),len(l)+len(u),0,2
    elif method=="blob_translated":
        total=0;sql=0
        with blob() as f:
            size=len(f);anchors={};translated={}
            def loc(x):
                nonlocal total,sql
                if x in translated:return translated[x]
                c=x//256*256
                if c not in anchors:
                    anchors[c]=con.execute(CHECK,(rid,c)).fetchone()[0];sql+=1
                y=anchors[c];n=x-c
                if n:
                    f.seek(y);part=f.read(min(4*n,size-y));total+=len(part)
                    # Excess trailing bytes may end in a partial multi-byte character.
                    prefix=part.decode("utf8","ignore")[:n];assert len(prefix)==n;y+=len(prefix.encode())
                translated[x]=y;return y
            out=[]
            for s in (a,b):
                start,end=loc(s["l"]),loc(s["h"]);f.seek(start);out.append(f.read(end-start))
        return tuple(out),total+sum(map(len,out)),sql,1
    else:raise KeyError(method)
    return out,sum(map(len,out)),sql,headers
def verify(r,name,result):
    out,transfer,sql,handles=result
    pieces=([r["right"]] if name=="text_right" else [r["both"][1]] if name=="text_half_right" else r["both"])
    assert len(out)==len(pieces) and all(sha(value)==s["sha"] for value,s in zip(out,pieces))
    if len(out)==2:assert sha(b"\n".join(s["header"].encode()+v for s,v in zip(pieces,out)))==r["wire"]
    assert transfer>=sum(len(x) for x in out)
    return transfer,sql,handles
def main():
    freeze();cases=load(D/"cases.json.gz");build=load(D/"build.json");assert build["db"]==sha_file(DB) and build["cases"]==sha_file(D/"cases.json.gz")
    rng=random.Random(26017);times=[];costs={};count=0
    con=connect()
    # Warm all source, checkpoint and query-plan pages for the persistent connection.
    for row in con.execute("select body from field"):pass
    for row in con.execute("select rid,c,b from checkpoint"):pass
    for k in METHODS:verify(cases[0],k,fetch(con,cases[0],k))
    for state,nround in (("warm",21),("fresh",3)):
        for i in range(nround):
            ix=list(range(len(cases)));rng.shuffle(ix)
            for j in ix:
                r=cases[j];order=list(METHODS);rng.shuffle(order)
                for k in order:
                    start=perf_counter_ns()
                    if state=="fresh":db=connect()
                    else:db=con
                    tic=perf_counter_ns();ans=fetch(db,r,k);toc=perf_counter_ns()
                    if state=="fresh":db.close()
                    finish=perf_counter_ns()
                    status=verify(r,k,ans);key=(j,k)
                    if key in costs:assert costs[key]==status
                    else:costs[key]=status
                    times.append([state,i,j,k,toc-tic,finish-start]);count+=1
    con.close()
    h=save(D/"measurements.json.gz",times);cc=save(D/"interface.json.gz",[[j,k,*v] for (j,k),v in sorted(costs.items())])
    out={"slices":h,"traffic":cc,"database":sha_file(DB),"plan":sha_file(D/"plan.json"),"bench":sha_file(Path(__file__)),"rounds":[21,3],"cases":len(cases),
         "calls_verified":count,"python":sys.version,"platform":platform.platform(),"processor":platform.processor(),"sqlite":sqlite3.sqlite_version,"mmap":0,"cache_kib":8192,"private_read_only":True}
    save(D/"measurement-seal.json",out);print(out)
if __name__=="__main__":main()

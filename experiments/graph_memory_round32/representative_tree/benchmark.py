"""Compare the weighted specialization of a representative tree with its packed winners."""
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from statistics import median
from time import perf_counter_ns
import random,sqlite3,sys,tempfile
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/"graph_memory_round31/support_pairs"))
from prepare import get,put,sha
EMPTY=255
MASK=[(1<<(e>>4))|(1<<(e&15)) for e in range(256)]
def build(edges):
    nodes=[EMPTY]*7
    def grow(i,banned):
        for e in edges:
            if banned&MASK[e]:continue
            nodes[i]=e
            if i<3:
                grow(2*i+1,banned|1<<(e>>4))
                grow(2*i+2,banned|1<<(e&15))
            break
    grow(0,0)
    return bytes(nodes)
def read(method,payload,bans,n):
    if n-bans.bit_count()<2:return EMPTY,0
    if method=="monien":
        i=0
        for depth in range(1,4):
            e=payload[i]
            if e==EMPTY or not MASK[e]&bans:return e,depth
            i=2*i+(1 if bans&(1<<(e>>4)) else 2)
        raise AssertionError("unexpected fourth level")
    for i,e in enumerate(payload,1):
        if not MASK[e]&bans:return e,i
    return EMPTY,len(payload)
def main():
    pair=HERE.parents[1]/"graph_memory_round31/support_pairs";data=get(pair/"rankings.json.gz");stored=get(pair/"cache-measurements.json.gz")
    names=("monien","packed_winners","full")
    put(HERE/"plan.json",{"rankings":sha(pair/"rankings.json.gz"),"protocol":sha(HERE/"PROTOCOL_RU.md"),"code":sha(Path(__file__)),"methods":names})
    plan_sha=sha(HERE/"plan.json");private=Path("D:/CodexResearch/x20-r32-representative-tree");private.mkdir(exist_ok=True)
    rec={};timed=[];timing=[];sizes={}
    from hashlib import sha256
    panel=sorted(data,key=lambda q:sha256(("r32-monien/"+q).encode()).digest())[:256]
    with tempfile.TemporaryDirectory(dir=private) as temp:
        root=Path(temp);db={m:sqlite3.connect(root/(m+".sqlite")) for m in names}
        try:
            for conn in db.values():conn.execute("create table t(id integer primary key,p blob not null)")
            for ix,(q,r) in enumerate(sorted(data.items())):
                full=bytes((i<<4)|j for i,j in r["pairs"]["joint"]);n=len(r["order"])
                tree=build(full);flat=bytes(full[j] for j in stored[q]["joint"]["2"]["tree"]);assert set(tree)-{EMPTY}==set(flat)
                arrays={"monien":tree,"packed_winners":flat,"full":full}
                for m,b in arrays.items():db[m].execute("insert into t values(?,?)",(ix,b))
                masks=[sum(1<<i for i in s) for k in range(3) for s in combinations(range(n),k)]
                probes={m:[0,0] for m in names};selected=[]
                for b in masks:
                    expected=read("full",full,b,n)[0]
                    for m,p in arrays.items():
                        e,c=read(m,p,b,n);assert e==expected;probes[m][0]+=c;probes[m][1]=max(c,probes[m][1])
                if q in panel:
                    randomized=sorted(masks,key=lambda b:sha256((q+"/"+str(b)).encode()).digest());selected=[0,1<<(full[0]>>4),MASK[full[0]],randomized[0]]
                    timed.extend((ix,n,num,b,read("full",full,b,n)[0]) for num,b in enumerate(selected))
                rec[q]={"events":len(masks),"probes":probes,"length":{m:len(p) for m,p in arrays.items()}}
            for m,conn in db.items():
                conn.commit();conn.execute("vacuum");assert conn.execute("pragma integrity_check").fetchone()==("ok",)
                sizes[m]=(root/(m+".sqlite")).stat().st_size
            for rep in range(6):
                rng=random.Random(320190+rep);jobs=[(i,n,tag,b,g,m) for i,n,tag,b,g in timed for m in names];rng.shuffle(jobs)
                for i,n,tag,b,g,m in jobs:
                    start=perf_counter_ns();p=db[m].execute("select p from t where id=?",(i,)).fetchone()[0]
                    actual,c=read(m,p,b,n);elapsed=perf_counter_ns()-start
                    assert actual==g
                    if rep:timing.append([i,tag,b,m,rep,elapsed])
        finally:
            for conn in db.values():conn.close()
    put(HERE/"cases.json.gz",rec);put(HERE/"timing.json.gz",timing)
    events=sum(r["events"] for r in rec.values());results={}
    for m in names:
        bins=defaultdict(list)
        for i,tag,b,mode,rep,ns in timing:
            if mode==m:bins[i,tag].append(ns/1000)
        medians=[median(a) for a in bins.values()]
        results[m]={"mean_probes":sum(r["probes"][m][0] for r in rec.values())/events,"max_probes":max(r["probes"][m][1] for r in rec.values()),
                    "payload":sum(r["length"][m] for r in rec.values()),"db_bytes":sizes[m],"p50_us":median(medians),"p95_us":float(np.quantile(medians,.95))}
    put(HERE/"results.json",{"plan":plan_sha,"n":len(rec),"events":events,"timed_events":len(timed),"timed_rows":len(timing),"methods":results})
if __name__=="__main__":main()

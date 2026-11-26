"""Profile actual SQLite reads and verify every returned pair against a full scan."""
import hashlib,random,statistics
from collections import Counter,defaultdict
from time import perf_counter_ns
import numpy as np
from store import HERE,PAIR,DBROOT,Store,code,mask,MODES,get,put,sha
def key(s):return hashlib.sha256(s.encode()).digest()
def make_events(q,rec):
    order=rec["pairs"]["joint"];n=len(rec["docs"]);ids=list(range(n))
    yield "none",()
    for size in range(1,min(4,n)+1):
        independent=sorted(ids,key=lambda i:key(q+"|pair-store|"+str(i)))[:size]
        yield "independent"+str(size),tuple(sorted(independent))
        chosen=[]
        while len(chosen)<size:
            feasible=next((p for p in order if all(i not in chosen for i in p)),None)
            options=feasible if feasible else [i for i in ids if i not in chosen]
            chosen.append(min(options,key=lambda i:key(q+"|pair-target|"+str(i))))
        yield "target"+str(size),tuple(sorted(chosen))
def main():
    build=get(HERE/"build.json");directory=DBROOT/build["database_directory_hash"]
    for mode,v in build["stores"].items():assert sha(directory/(mode+".sqlite"))==v["sha"]
    ranks=get(PAIR/"rankings.json.gz");all_q=sorted(ranks);indices={q:i for i,q in enumerate(all_q)}
    panel=sorted(all_q,key=lambda q:key("store-preregister-v1/"+q))[:128]
    methods=("rows","full","raw","basis","tree","lookup","tree_certificate");db=Store(directory)
    events=[];expected={}
    for q in panel:
        rec=ranks[q];n=len(rec["order"]);i=indices[q]
        for label,removed in make_events(q,rec):
            gt=next((code(a,b) for a,b in rec["pairs"]["joint"] if a not in removed and b not in removed),255)
            events.append([q,i,n,label,removed,gt])
    put(HERE/"timing-plan.json",{"panel":panel,"events":len(events),"code":sha(HERE/"profile.py"),"prior":sha(HERE/"build.json"),"methods":methods})
    for q,i,n,label,removed,gt in events:
        for mode in methods:
            got=db.query(mode,i,n,removed);assert got[0]==gt,(q,mode,removed,got,gt)
            expected[q,label,mode]=got
    logs=[]
    for rep in range(5):
        rng=random.Random(31072+rep);order=list(events);rng.shuffle(order)
        for q,i,n,label,removed,gt in order:
            modes=list(methods);rng.shuffle(modes)
            for mode in modes:
                start=perf_counter_ns();answer,calls,bytes_read,route=db.query(mode,i,n,removed);elapsed=perf_counter_ns()-start
                assert (answer,calls,bytes_read,route)==expected[q,label,mode] and answer==gt
                logs.append([q,label,len(removed),mode,rep,elapsed,calls,bytes_read,route,answer])
    db.close();put(HERE/"timing.json.gz",logs)
    stats={}
    for condition,match in [("within",lambda n:n<=2),("outside",lambda n:n>2),("two",lambda n:n==2),("four",lambda n:n==4)]:
        stats[condition]={}
        for m in methods:
            rows=[r for r in logs if r[3]==m and match(r[2])];by=defaultdict(list);routes=Counter()
            for q,label,n,mo,rep,ns,queries,wire,route,_ in rows:
                by[q,label].append(ns/1000)
                if rep==0:routes[route]+=1
            med=[statistics.median(v) for v in by.values()]
            stats[condition][m]={"n":len(by),"p50_us":statistics.median(med),"p95_us":float(np.quantile(med,.95)),
                 "mean_sql":statistics.mean(r[6] for r in rows),"mean_returned_bytes":statistics.mean(r[7] for r in rows),"routes":dict(routes)}
    put(HERE/"results.json",{"rows":len(logs),"events":len(events),"questions":len(panel),"summary":stats,"timing_sha":sha(HERE/"timing.json.gz")})
if __name__=="__main__":main()

"""Compare lazy durable promotion with a one-episode process-local lexical cache."""
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import random
import sqlite3
import sys
from time import perf_counter_ns as now
from ingest import (HERE,VIEW,PRIVATE,DB,priority,open_database,write_episode,run_query,
                    decode,pack,read,write,sha,counts,postings,save_postings,select)

METHODS = ("raw","eager","minimal_1","minimal_3","resident","resident3")
def heap_bytes(root):
    seen=set()
    def size(obj):
        k=id(obj)
        if k in seen:
            return 0
        seen.add(k)
        total=sys.getsizeof(obj)
        if isinstance(obj,dict):
            return total+sum(size(k)+size(v) for k,v in obj.items())
        if isinstance(obj,(tuple,list)):
            return total+sum(size(x) for x in obj)
        return total
    return size(root)

def issue(db,sid,method,number,query,cache):
    if method in ("raw","eager"):
        return run_query(db,sid,query,method,number)
    promote_at = {"minimal_1":1, "minimal_3":3}.get(method)
    if promote_at is not None and number != promote_at:
        previous = "eager" if number > promote_at else "raw"
        return run_query(db,sid,query,previous,number)
    start=now()
    if method=="resident3" and (number-1)%3==0:
        cache.clear()
    traffic=0
    if not cache:
        coords,_ = decode(db.execute("SELECT data FROM head WHERE s=?",(sid,)).fetchone()[0])
        bodies=[row[0] for row in db.execute("SELECT body FROM win WHERE s=? ORDER BY i",(sid,))]
        traffic=sum(map(len,bodies))
        docs=counts(bodies)
        lengths=[sum(doc.values()) for doc in docs]
        table=postings(docs)
        view={"rows":[{"coords":c,"length":n} for c,n in zip(coords,lengths)]}
        if promote_at is not None:
            with db:
                db.execute("UPDATE head SET data=? WHERE s=?",(pack([coords,lengths]),sid))
                save_postings(db,sid,table)
        index={w:dict(entries) for w,entries in table.items()}
        if method.startswith("resident"):
            cache["model"]=(view,index)
    else:
        view,index=cache["model"]
    winner=select(view,query,"inverted",None,index)
    return [now()-start,traffic,winner]

def main():
    src=sqlite3.connect(DB.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    pri=read(HERE/"plan.json")
    assert sha(DB)==pri["source"]
    lock={"first":sha(HERE/"receipt.json"),"code":sha(Path(__file__)),"protocol":sha(HERE/"PROMOTION_RU.md")}
    lockfile=HERE/"promotion-lock.json"
    if lockfile.exists():
        assert read(lockfile)==lock
    else:
        write(lockfile,lock)
    ref={(r["g"],r["q"]):r["ref"] for r in read(VIEW/"decisions.json.gz")}
    results=[];heaps={};sizes=[]
    for rep in range(3):
        with TemporaryDirectory(dir=PRIVATE) as tmp:
            paths={m:Path(tmp)/(m+".sqlite") for m in METHODS}
            dbs={m:open_database(p) for m,p in paths.items()}
            order=list(enumerate(pri["cohort"],1));random.Random(273169+rep).shuffle(order)
            for sid,(key,corpus) in order:
                v=decode(src.execute("SELECT projected FROM snapshot WHERE sid=?",(key,)).fetchone()[0])
                coords=[r["coords"] for r in v["rows"]]
                bodies=[r[0] for r in src.execute("SELECT body FROM payload WHERE sid=? ORDER BY idx",(key,))]
                queries=sorted(src.execute("SELECT q,question FROM future WHERE sid=?",(key,)),key=lambda r:priority(r[0]))
                scheduled=list(METHODS);random.Random(priority("promotion"+str(rep)+key)).shuffle(scheduled)
                for method in scheduled:
                    db=dbs[method]
                    ingest=write_episode(db,sid,coords,bodies,"eager" if method=="eager" else "raw")
                    cache={};times=[]
                    for i,(q,query) in enumerate(queries,1):
                        elapsed,traffic,winner=issue(db,sid,method,i,query,cache)
                        assert winner==ref[key,q]
                        times.append([q,elapsed,traffic,winner])
                    results.append([rep,corpus,key,method,ingest,times])
                    if rep==0 and method=="resident":
                        heaps[key]=[corpus,heap_bytes(cache),sum(map(len,bodies))]
            for method,db in dbs.items():
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
                db.close();sizes.append([rep,method,paths[method].stat().st_size])
        print("completed control",rep,flush=True)
    src.close()
    write(HERE/"promotion-times.json.gz",results);write(HERE/"resident-heap.json",heaps);write(HERE/"promotion-sizes.json",sizes)
    write(HERE/"promotion-receipt.json",{"lock":sha(lockfile),"times":sha(HERE/"promotion-times.json.gz"),
          "heap":sha(HERE/"resident-heap.json"),"sizes":sha(HERE/"promotion-sizes.json"),
          "runs":len(results),"answers":sum(len(r[-1]) for r in results)})
if __name__=="__main__":
    main()


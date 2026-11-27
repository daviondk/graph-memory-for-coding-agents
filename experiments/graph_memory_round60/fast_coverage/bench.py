"""Randomized warm-store comparison. Each arm owns and updates its own complete hot state."""
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
from random import Random
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns as clock
import argparse
import platform
import sqlite3
from residual import EXP,BlockStore,Coverage,Fast,Hot,Residual,load,possible_losses,prepare,save
HERE=Path(__file__).resolve().parent
SEED=60172
ARMS=("append","xor_native","notified","native_count","native_bare","residual_only")
GROUPS={"r59":EXP/"graph_memory_round59/holdout/events.json.gz","r60":HERE.parent/"panel/events.json.gz"}

def reader(db,cap,mode):
    if mode=="notified":return Coverage(db,Hot(),cap,True)
    if mode in ("append","xor_native"):return Fast(db,Hot(),mode,cap)
    return Residual(db,cap,mode)

def update(h,j,ids):
    if isinstance(h,Residual):
        h.committed(j,ids)
    elif isinstance(h,Coverage):
        candidates=possible_losses(h.hot,ids)
        h.hot.append(j,ids)
        losses=[(k,candidates[k]) for k in sorted(candidates) if k not in h.hot.live]
        h.after_committed(j,ids,losses)
    else:
        h.hot.append(j,ids)
        h.after_write(j,ids)

def run_case(path,ops,rng):
    cut=sum(x[0]=="w" for x in ops)//2
    db=BlockStore(path,"filelist",True)
    readers={}
    counts=defaultdict(Counter)
    digest=sha256()
    audit=[]
    sql_pre=sql_post=0; writes=0
    for op in ops:
        if db.next_id==cut and not readers:
            db.close();db=BlockStore(path,"filelist")
            for table,col in (("posting","js"),("event","members")):
                sum(len(v[0]) for v in db.db.execute("SELECT "+col+" FROM "+table))
            readers={str(cap)+"/"+mode:reader(db,cap,mode) for cap in (1024,4096) for mode in ARMS}
        if op[0]=="w":
            _,j,rev,ids=op
            t=clock();assert db.append(j,rev,ids);elapsed=clock()-t
            if readers:sql_post+=elapsed;writes+=1
            else:sql_pre+=elapsed
            for k in rng.sample(list(readers),len(readers)):
                h=readers[k]
                t=clock();update(h,j,ids);counts[k]["update_ns"]+=clock()-t
                assert h.cache.size<=h.cache.limit
        elif readers:
            _,f,tie,prior,gold=op
            stats={}
            for k in rng.sample(list(readers),len(readers)):
                h=readers[k]
                t=clock();ans,s=h.read(f,tie,prior);counts[k]["read_ns"]+=clock()-t
                assert ans==gold and h.cache.size<=h.cache.limit
                v=[s["posting_bytes"],s["body_bytes"],s["posting_calls"],s["body_calls"]]
                stats[k]=v
                for m,n in zip(("posting","bodies","posting_calls","body_calls"),v):
                    counts[k][m]+=n
            digest.update(repr((db.next_id,f,ans)).encode())
            audit.append([db.next_id,f,stats])
    for k,h in readers.items():
        sizes=h.cache.inventory()
        counts[k].update(cache_packed=sizes["packed"],sampled_python=sizes["python"],replacements=sizes["evicted"],write_updates=h.cache.updates)
        if isinstance(h,Residual):counts[k].update(h.stats)
    db.close()
    return dict(sql_pre=sql_pre,sql_after=sql_post,writes_after=writes,n=len(audit),rank_digest=digest.hexdigest(),queries=audit,counters=counts)

def measures(blocks):
    out={}
    for g in ("r59","r60","both"):
        rows=[]
        for b in blocks:
            projects=[v for k,v in b.items() if g=="both" or k.startswith(g+"/")]
            totals={k:sum((Counter(p["counters"][k]) for p in projects),Counter()) for k in projects[0]["counters"]}
            for k,x in totals.items():
                x["total_ns"]=x["read_ns"]+x["update_ns"]
                x["traffic"]=x["posting"]+x["bodies"]
                x["mixed_ns"]=x["total_ns"]+sum(p["sql_after"] for p in projects)
            rows.append(totals)
        keys=("read_ns","update_ns","total_ns","mixed_ns","traffic","posting","bodies","posting_calls","body_calls","exception_inserts","max_lru_backlog","max_hot_backlog")
        methods={k:{m:[row[k][m] for row in rows] for m in keys} for k in rows[0]}
        paired={}
        for cap in (1024,4096):
            for mode in ARMS:
                k=f"{cap}/{mode}";b=f"{cap}/append"
                per={repo:(p["counters"][k]["bodies"]+p["counters"][k]["posting"])-(p["counters"][b]["bodies"]+p["counters"][b]["posting"]) for repo,p in blocks[0].items() if g=="both" or repo.startswith(g+"/")}
                paired[k]={"vs_append_ns":[row[k]["total_ns"]-row[b]["total_ns"] for row in rows],"delta_by_repo":per,
                           "byte_wtl":[sum(x<0 for x in per.values()),sum(x==0 for x in per.values()),sum(x>0 for x in per.values())]}
        out[g]=dict(methods=methods,paired=paired)
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument("--verify",action="store_true");args=p.parse_args()
    raw=HERE/"runs.json.gz";dest=HERE/"results.json"
    if args.verify:
        saved=load(raw)
        for n,h in saved["hashes"].items():assert sha256((HERE/n).read_bytes()).hexdigest()==h
        blocks=saved["blocks"];assert measures(blocks)==load(dest)
    else:
        ops={g+"/"+repo:prepare(s,"B")[0] for g,f in GROUPS.items() for repo,s in load(f).items()}
        rng=Random(SEED);blocks=[]
        hashes={n:sha256((HERE/n).read_bytes()).hexdigest() for n in ("PROTOCOL.md","residual.py","bench.py")}
        with TemporaryDirectory(dir=HERE) as tmp:
            path=Path(tmp)/"history.sqlite"
            for rep in range(5):
                block={}
                for k in rng.sample(list(ops),len(ops)):
                    c=run_case(path,ops[k],rng);path.unlink()
                    if blocks:
                        assert c["queries"]==blocks[0][k]["queries"] and c["rank_digest"]==blocks[0][k]["rank_digest"]
                        del c["queries"]
                    block[k]=c
                blocks.append(block)
                print("block",rep+1,len(block),flush=True)
        save(raw,dict(blocks=blocks,hashes=hashes,sources={g:sha256(f.read_bytes()).hexdigest() for g,f in GROUPS.items()},seed=SEED,
                      python=platform.python_version(),sqlite=sqlite3.sqlite_version))
        save(dest,measures(blocks))
    print("exact checks",sum(p["n"]*len(p["counters"]) for block in blocks for p in block.values()))
if __name__=="__main__":main()


"""Check dependence on amortizing SQLite read locks without changing the primary protocol."""
import random
from time import perf_counter_ns as now
from collections import defaultdict
import numpy as np
from control import D,PAR,plan,read,save,sha,pack,lookup,open_db,PRIMARY

def main():
    p,cases,views,old,new=plan();oracle=read(PAR/"reference.json.gz")
    work=[(ix,q,c,*oracle[q][c]["ban"]) for ix,q in enumerate(p["qids"]) if q in p["panel"] for c in ("winner","record","random")]
    db=open_db(old,new,False);db.execute("PRAGMA query_only=1")
    rng=random.Random(28311);out=[]
    for block in range(18):
        configurations=["per_statement","shared_snapshot"]
        if block%2:configurations.reverse()
        for mode in configurations:
            if mode=="shared_snapshot":db.execute("BEGIN")
            seq=[(ix,q,c,l,h,m) for ix,q,c,l,h in work for m in ("sky",PRIMARY)]
            rng.shuffle(seq)
            for ix,q,c,l,h,m in seq:
                t=now();v,stats=lookup(db,m,ix,l,h);value=pack(v);ns=now()-t
                assert value==pack(oracle[q][c]["answer"])
                if block>=2:out.append([block,q,c,m,mode,ns])
            if mode=="shared_snapshot":db.execute("COMMIT")
    db.close();save(D/"transaction-samples.json.gz",out)
    groups=defaultdict(list)
    for _,q,c,m,mode,ns in out:groups[q,c,m,mode].append(ns/1e3)
    result={}
    for mode in ("per_statement","shared_snapshot"):
        result[mode]={}
        for m in ("sky",PRIMARY):
            query=[np.median(v) for (q,c,arm,md),v in groups.items() if arm==m and md==mode]
            result[mode][m]={"q":len(query),"p50_us":float(np.median(query)),"p95_us":float(np.percentile(query,95))}
    save(D/"transaction-results.json",{"protocol":sha(D/"TRANSACTION_RU.md"),"code":sha(D/"transaction.py"),
            "samples":sha(D/"transaction-samples.json.gz"),"n":len(out),"result":result});print(result)
if __name__=="__main__":main()

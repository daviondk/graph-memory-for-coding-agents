"""Blocked randomized reads on the sealed common SQLite state, separately for ID and score."""
from compare import D, TEMP_ROOT, PLANS, plan_setup, read_pair, oracle, advance, connect, create_base
from engine import statement
import json
import gzip
import sqlite3
import hashlib
from pathlib import Path
import shutil
import random
from tempfile import TemporaryDirectory
from time import perf_counter_ns
import numpy as np

NAMES=("address","journal","eligible")
BLOCKS=32
def sql_for(plan,contract):
    if contract=="score":return read_pair(plan)
    if plan in ("address","journal"):
        return "SELECT id FROM history WHERE q=?1 AND step<=?2 ORDER BY step DESC LIMIT 1"
    return statement(plan,False)

def main():
    z=D.parent/"maintenance"/"workload.json.gz";data=json.loads(gzip.decompress(z.read_bytes()))
    seq=list(range(len(data)));random.Random(525200).shuffle(seq)
    cells=[[(q,t,oracle(data[q]["candidates"],t)) for q in seq[b::BLOCKS] for t in range(data[q]["cuts"]+1)] for b in range(BLOCKS)]
    schedule=[];samples=np.empty((8,2,3,BLOCKS),dtype=np.int64)
    with TemporaryDirectory(dir=TEMP_ROOT) as folder:
        folder=Path(folder);base=folder/"base.sqlite";create_base(base,enumerate(data));connections={}
        try:
            for plan in NAMES:
                path=folder/(plan+".sqlite");shutil.copyfile(base,path);db=connect(path);connections[plan]=db
                plan_setup(db,plan)
                for q,e in enumerate(data):
                    for t in range(1,e["cuts"]+1):advance(db,q,t,[v[0] for v in e["candidates"] if v[4]==t])
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            def trial(b,db,sql,contract):
                ticks=perf_counter_ns()
                got=[db.execute(sql,(q,t)).fetchone() for q,t,_ in cells[b]]
                elapsed=perf_counter_ns()-ticks
                expected=[r if contract=="score" else r[:1] for _,_,r in cells[b]]
                assert got==expected
                return elapsed
            for rep in range(-1,8):
                blocks=list(range(BLOCKS));arms=[(i,j) for i in range(2) for j in range(3)]
                rng=random.Random(525400+rep);rng.shuffle(blocks);rng.shuffle(arms)
                if rep>=0:schedule.append([blocks,arms])
                for i,j in arms:
                    contract=("id","score")[i];plan=NAMES[j];sql=sql_for(plan,contract)
                    for b in blocks:
                        e=trial(b,connections[plan],sql,contract)
                        if rep>=0:samples[rep,i,j,b]=e
        finally:
            for db in connections.values():db.close()
    rng=np.random.default_rng(525430);obs=samples.sum(3).mean(0);result={}
    num=sum(map(len,cells))
    for i,contract in enumerate(("id","score")):
        boot=[]
        for _ in range(100):
            repeats=rng.integers(0,8,(100,8,1));blocks=rng.integers(0,BLOCKS,(100,1,BLOCKS))
            a=np.moveaxis(samples[:,i],1,-1)
            boot.extend(a[repeats,blocks].sum(axis=(1,2))/a[repeats,blocks].sum(axis=(1,2))[:,0,None])
        ci=np.quantile(boot,[.025,.975],axis=0)
        result[contract]={name:dict(us=obs[i,j]/num/1000,relative_to_address=obs[i,j]/obs[i,0],
                                   ci=ci[:,j].tolist()) for j,name in enumerate(NAMES)}
    raw=dict(schedule=schedule,contracts=["id","score"],plans=NAMES,samples_ns=samples.tolist())
    (D/"read-timings.json.gz").write_bytes(gzip.compress(json.dumps(raw,separators=(",",":")).encode(),mtime=0))
    out=dict(queries=num,repeats=8,blocks=BLOCKS,sqlite=sqlite3.sqlite_version,contrasts=result,
             protocol=hashlib.sha256((D/"LATENCY_PROTOCOL_RU.md").read_bytes()).hexdigest())
    (D/"latency.json").write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(result)
if __name__=="__main__":main()


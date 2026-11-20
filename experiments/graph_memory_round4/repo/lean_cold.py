"""End-to-end CPU microbenchmark on distinct archival repositories without reading target labels."""
import os
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[key]="1"
import gc,gzip,hashlib,json,pickle,random,statistics,time
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from data_io import rows
from memory import encode,record,features
from lean_graph import Lean
from incremental_precise import cycles
D=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    paths=sorted((D/"archive_inputs").glob("*.parquet"));assert len(paths)==4
    prior={json.loads(line)[2] for line in gzip.open(D/"archive_streaming.jsonl.gz","rt")}
    used=set(prior);roster={}
    for p in paths:
        names=pq.read_table(p,columns=["repo_name"]).column(0).to_pylist()
        ids=[]
        for j in sorted(range(len(names)),key=lambda j:hashlib.sha256(("r4cold|"+p.stem+"|"+str(j)).encode()).digest()):
            if names[j] in used:continue
            used.add(names[j]);ids.append(j)
            if len(ids)==24:break
        assert len(ids)==24;roster[p.name]=sorted(ids)
    lock={"roster":roster,"projects_excluded":len(prior),"sha":{p.name:digest(p) for p in [*paths,D/"LEAN_COLD_RU.md",Path(__file__),D/"lean_graph.py",D/"models.pkl"]}}
    (D/"lean_cold_lock.json").write_text(json.dumps(lock),encoding="utf8")
    with (D/"models.pkl").open("rb") as fp:model=pickle.load(fp)[3,"graph"]
    logs=[]
    for p in paths:
        need=set(roster[p.name])
        for j,row in enumerate(rows(p,["repo_name","code","context"])):
            if j not in need:continue
            texts=row["context"];q="\n".join(row["code"].splitlines()[-3:])
            def trial(kind,rank):
                record.cache_clear();gc.collect();g=Lean(True) if kind=="live" else None;out=[]
                wall=time.perf_counter_ns();start=cycles()
                for i,t in enumerate(texts):
                    if g:g.add(record(t));v=g.view()
                    else:v=encode(texts[:i+1])
                    if rank:
                        a=features(q,v,3);score=model.predict_proba(a)[:,1]
                        out.append(np.argsort(-score,kind="stable").tolist())
                return cycles()-start,time.perf_counter_ns()-wall,out
            arms=[(k,rank) for k in ("rebuild","live") for rank in (False,True)]
            random.Random("r4cold|"+str(j)).shuffle(arms);a={};ref=None
            for seq in (arms,list(reversed(arms))):
                for k,rank in seq:
                    c,w,o=trial(k,rank);a.setdefault(k+("_rank" if rank else "_graph"),[]).append([c,w])
                    if rank and ref is not None:assert o==ref
                    if rank:ref=o
            logs.append(dict(id=[p.name,j],repo=row["repo_name"],n=len(texts),times=a,ranks=ref))
    assert len(logs)==len({v["repo"] for v in logs})==96
    (D/"lean_cold_items.json.gz").write_bytes(gzip.compress(json.dumps(logs,separators=(",",":")).encode(),mtime=0))
    out={"projects":96,"checkpoints":sum(s["n"] for s in logs),"times":{}}
    for f in ("graph","rank"):
        for unit,i in (("cycle",0),("wall_ns",1)):
            pts=np.array([[statistics.mean(y[i] for y in v["times"][k+"_"+f]) for k in ("rebuild","live")] for v in logs])
            b=pts[np.random.default_rng(1067).integers(96,size=(10000,96))].sum(axis=1);z=pts.sum(axis=0)
            out["times"][f+"_"+unit]={"sum":z.tolist(),"speedup":z[0]/z[1],"ci":np.quantile(b[:,0]/b[:,1],[.025,.975]).tolist()}
    (D/"lean_cold_results.json").write_text(json.dumps(out,indent=2),encoding="utf8");print(out)
if __name__=="__main__":main()


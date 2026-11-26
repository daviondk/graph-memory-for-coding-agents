"""Fresh disjoint trajectories, blinded execution order and a same-policy negative control."""
import gzip
import hashlib
import json
import statistics
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np

D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"sqlite_revocation"))
import benchmark as bench

def main():
    assert bench.sha((bench.D/"manifest.json").read_bytes())=="bda82e51c4cfd7066da3c6be247d358e883e1e3659f66efc7285c35af343f4f7"
    original=bench.load(bench.D/"plan.json")
    stream={}
    for i in range(8):
        p=bench.SOURCE/f"operations-{i}.json.gz"
        assert bench.sha(p.read_bytes())==original["inputs"][p.name]
        stream.update(bench.load(p))
    ordered=sorted(stream,key=lambda h:bench.sha(("sqlite-revocation-v1/"+h).encode()))
    assert original["histories"]==ordered[:64]
    cohort=ordered[64:128]
    methods=["exact","before_read","sham_left","sham_right"]
    bench.save(D/"plan.json",dict(histories=cohort,control_manifest=bench.sha((bench.D/"manifest.json").read_bytes()),
                   code=bench.sha(Path(__file__).read_bytes()),protocol=bench.sha((D/"PROTOCOL_RU.md").read_bytes()),
                   schedule="counterbalanced 4x4 cyclic",sqlite=bench.sqlite3.sqlite_version))
    plans={h:{m:bench.schedule(stream[h]["log"],"before_read" if m=="before_read" else "exact")[0] for m in methods} for h in cohort}
    out=[]
    with TemporaryDirectory(dir=bench.ROOT) as scratch:
        for rep in range(4):
            for h in sorted(cohort,key=lambda h:bench.sha((str(rep)+"sql-rep/"+h).encode())):
                k=(rep+int(bench.sha(("sql-position/"+h).encode())[:8],16))%4
                for position,m in enumerate(methods[k:]+methods[:k]):
                    with TemporaryDirectory(dir=scratch) as tmp:
                        r=bench.execute(Path(tmp)/"edges.sqlite",plans[h][m])
                    out.append(dict(trajectory=h,method=m,rep=rep,position=position,**r))
    bench.save(D/"runs.json.gz",out)
    assess(out,cohort,methods)

def assess(out,cohort,methods):
    assert len(out)==1024
    for h in cohort:
        rows=[r for r in out if r["trajectory"]==h]
        assert len({r["observed"] for r in rows})==1 and sum(r["reads"] for r in rows)==80
        for method in methods:
            r=[x for x in rows if x["method"]==method]
            assert set(x["position"] for x in r)==set(range(4))
    random=np.random.default_rng(351127)
    ix=random.integers(64,size=(10000,64))
    results={}
    for field in ("ms","before_checkpoint_ms","wal","tx"):
        x=np.asarray([[statistics.median(r[field] for r in out if r["trajectory"]==h and r["method"]==m) for m in methods] for h in cohort])
        d=x[:,0]-x[:,1];s=x[:,2]-x[:,3]
        metrics=np.column_stack([d,s,d-s])
        bootstrap=metrics[ix].mean(1)
        ratio=x[ix,0].mean(1)/x[ix,1].mean(1)
        results[field]=dict(means=x.mean(0).tolist(),differences=metrics.mean(0).tolist(),
                  pairedCI=np.quantile(bootstrap,[.025,.975],axis=0).tolist(),ratio=float(x[:,0].mean()/x[:,1].mean()),
                  ratioCI=np.quantile(ratio,[.025,.975]).tolist())
    bench.save(D/"results.json",dict(measurements=len(out),methods=methods,
                  difference_order=["exact-before_read","sham_left-sham_right","difference_of_differences"],summaries=results,
                  plan=bench.sha((D/"plan.json").read_bytes()),measurements_hash=bench.sha((D/"runs.json.gz").read_bytes())))

if __name__=="__main__":main()


import os,sys,importlib.util,gzip,time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
D=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('schema_runner',D/'run.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
GRID=[512,1024,2048,4096,8192]
def predict(job):
    b,k=job;dest=D/f'profile_{b}';r.HERE=dest;r.BUDGET=b
    original=r.memory.transition
    with gzip.open(dest/f'latency_{k}.gz','wt',encoding='utf8') as of:
        def timed(method,blob,event,static,weights,budget):
            tick=time.perf_counter_ns();value=original(method,blob,event,static,weights,budget)
            of.write(str(time.perf_counter_ns()-tick)+'\n')
            return value
        r.memory.transition=timed
        try:r.predict(k)
        finally:r.memory.transition=original
    return job
def collect():
    result={}
    primary=r.read(D/'results.json')
    for b in GRID:
        target=D/f'profile_{b}';r.HERE=target;r.BUDGET=b;r.score();result[str(b)]={}
        z=r.read(target/'results.json')
        if b in (4096,1024):
            prev=D if b==4096 else D/'sensitivity_1024'
            for k in range(8):
                for p,q in zip(r.rows(prev/f'events_{k}.gz'),r.rows(target/f'events_{k}.gz'),strict=True):
                    assert p[:2]==q[:2]
                    assert all(p[2][arm][:-1]==q[2][arm][:-1] for arm in r.ARMS)
        times={a:[] for a in r.ARMS}
        for k in range(8):
            with gzip.open(target/f'latency_{k}.gz','rt') as fp:
                for j,s in enumerate(fp):times[r.ARMS[j%3]].append(int(s)/1e6)
        for a in r.ARMS:
            c=z['cost'][a];v=times[a];assert len(v)==c['steps']
            result[str(b)][a]=dict(full=z['counts'][a],line_coverage=z['metrics_full_coverage_first'][a][1],avg_bytes=c['mean_bytes_total']/c['steps'],max_bytes=c['max_bytes'],size_same_state=c['same_state_bytes_sum']/c['cuts'],avg_kept_lines=c['resident_lines_sum']/c['cuts'],avg_ms=float(np.mean(v)),median_ms=float(np.median(v)),p95_ms=float(np.quantile(v,.95)),primary_pair=z['contrasts']['edges-generic'] if a=='edges' else None)
    r.save(D/'profile_results.json',result)
def main():
    if sys.argv[1]=='score':collect();return
    lock={p.name:r.sha(p) for p in [D/'SWEEP.md',D/'sweep.py',D/'schema_codec.py',D/'run.py',D/'results.json',D/'sensitivity_1024'/'checkpoint_lock.json']}
    r.save(D/'profile_method_lock.json',lock)
    for b in GRID:
        dest=D/f'profile_{b}';dest.mkdir(exist_ok=True);assert not (dest/'checkpoint_lock.json').exists()
        for p in D.glob('source_*.jsonl.gz'):
            if not (dest/p.name).exists():os.link(p,dest/p.name)
    with ProcessPoolExecutor(3) as pool:
        for b,k in pool.map(predict,[(b,k) for b in GRID for k in range(8)]):
            print('completed',b,k,flush=True)
    for b in GRID:
        dest=D/f'profile_{b}';blobs=[p for g in ('cuts_*.gz','events_*.gz','latency_*.gz') for p in dest.glob(g)]
        assert len(blobs)==24
        r.save(dest/'checkpoint_lock.json',{p.name:r.sha(p) for p in blobs})
if __name__=='__main__':main()

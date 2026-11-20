import os,sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location('schema_runner',Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
D=Path(__file__).resolve().parent;DEST=D/'sensitivity_1024'
def partial(k):
    r.HERE=DEST;r.BUDGET=1024
    return r.predict(k)
if __name__=='__main__':
    if sys.argv[1]=='predict':
        DEST.mkdir(exist_ok=True)
        assert not (DEST/'checkpoint_lock.json').exists()
        for p in D.glob('source_*.jsonl.gz'):
            dest=DEST/p.name
            if not dest.exists():os.link(p,dest)
        r.save(DEST/'method_lock.json',{p.name:r.sha(p) for p in [D/'SENSITIVITY.md',D/'run.py',D/'sensitivity.py',D/'results.json',D/'checkpoint_lock.json']})
        with ProcessPoolExecutor(3) as pool:
            for k in pool.map(partial,range(8)):print('completed shard',k,flush=True)
        blobs=[p for g in ('cuts_*.gz','events_*.gz') for p in DEST.glob(g)]
        assert len(blobs)==16;r.save(DEST/'checkpoint_lock.json',{p.name:r.sha(p) for p in blobs})
    else:
        r.HERE=DEST;r.BUDGET=1024;r.score()



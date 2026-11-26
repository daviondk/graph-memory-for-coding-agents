"""Secondary CPU cycles and a locality stress test on the same ordered per-trajectory input."""
import ctypes
from ctypes import wintypes
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter_ns as wall
import random
from run import D,BASE,sha,read,save,make

ARMS=('scan','scan_memo','exact','exact_memo','deferred','deferred_memo','eager')
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.GetCurrentThread.restype=wintypes.HANDLE
kernel.QueryThreadCycleTime.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_ulonglong)]
kernel.QueryThreadCycleTime.restype=wintypes.BOOL
handle=kernel.GetCurrentThread()
def cycles():
    v=ctypes.c_ulonglong()
    if not kernel.QueryThreadCycleTime(handle,ctypes.byref(v)):raise ctypes.WinError(ctypes.get_last_error())
    return v.value
def execute(fix,mode,rep):
    order=[(t,j) for t,frames in enumerate(fix) for j in range(len(frames))]
    if mode=='interleaved':order.sort(key=lambda tj:(tj[1],tj[0]))
    rng=random.Random(461301+rep)
    result={k:[[0,0,0,0] for tr in fix] for k in ARMS}
    with TemporaryDirectory(dir=D) as tmp:
        dbs={k:make(Path(tmp)/(k+'.sqlite'),k) for k in ARMS}
        try:
            for t,j in order:
                delta,rows=fix[t][j];gold=dict(rows);arms=list(ARMS);rng.shuffle(arms)
                for k in arms:
                    reader=dbs[k];h=reader.n_hits;calls=reader.n_queries
                    a=cycles();b=wall();reader.apply(t,delta);out=reader.read(t);ns=wall()-b;cc=cycles()-a
                    assert out==gold
                    r=result[k][t];r[0]+=ns;r[1]+=cc;r[2]+=reader.n_hits-h;r[3]+=reader.n_queries-calls
        finally:
            for reader in dbs.values():reader.db.close()
    return result
def main():
    fix=read(BASE/'normalized.json.gz')
    meta={'protocol':sha(D/'INTERLEAVE_PROTOCOL_RU.md'),'code':sha(Path(__file__)),'prior':sha(D/'results.json'),'arms':list(ARMS),'fields':['wall_ns','thread_cycles','hits','probes']}
    save(D/'interleave-registration.json',meta)
    for rep in range(3):
        for mode in (('serial','interleaved') if rep%2==0 else ('interleaved','serial')):
            p=D/f'cycle-{rep}-{mode}.json.gz';assert not p.exists()
            out=execute(fix,mode,rep);save(p,out);print(rep,mode,flush=True)
    save(D/'cycles-seal.json',{'registration':sha(D/'interleave-registration.json'),'runs':{p.name:sha(p) for p in sorted(D.glob('cycle-*.json.gz'))}})
if __name__=='__main__':main()


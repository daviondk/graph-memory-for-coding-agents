"""Cross forest specialization and packet-aware lazy evaluation at matched input and output."""
import ctypes as ct
import gzip
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from time import perf_counter_ns
for var in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
    os.environ[var] = "1"
import numpy as np

D = Path(__file__).resolve().parent
BASE = D.parent/"matched_reader"
sys.path.insert(0,str(BASE))
from runtime import Reader, arrays, read
from common import SEEDS, put, sha
from run_matched import select

PROTOCOL = "66403d6af5b0cd602321343594f5fdfd5b91bfcb18567e53442831e972633f07"
MODES = ("generic_eager","generic_lazy","compiled_eager","compiled_lazy")

def open_library():
    lib = ct.CDLL(str(D/"scoring.dll"))
    p, i = ct.c_void_p,ct.c_int
    lib.undecided.argtypes = [i,p,p,p]
    lib.undecided.restype = i
    lib.evaluate.argtypes = [i,p,i,i,p,p,ct.c_double,p,p]
    lib.evaluate.restype = None
    return lib


class Plans:
    def __init__(self):
        self.reader = Reader()
        self.kernel = open_library()
        self.solve = self.reader.lib.packet
        self.solve.argtypes = [ct.c_int]*3 + [ct.c_void_p]*4
        self.solve.restype = ct.c_int

    def scores(self,p,mode):
        reader = self.reader
        costs, order = p["costs"],p["order"]
        n = count = len(costs)
        mask = None
        if mode % 2:
            mask = np.empty(n,np.int32)
            count = self.kernel.undecided(n,order.ctypes.data,costs.ctypes.data,mask.ctypes.data)
            if count == 0:
                return np.ones(n),mask[:0],count
            logits = np.zeros(n)
        else:
            logits = np.empty(n)
        x = reader.features(p)
        self.kernel.evaluate(count,mask.ctypes.data if mask is not None else None,int(mode>=2),
            len(reader.roots),reader.roots.ctypes.data,reader.tables.ctypes.data,reader.base,x.ctypes.data,logits.ctypes.data)
        return np.logaddexp(0,logits),mask[:count] if mask is not None else slice(None),count

    def run(self,p,mode):
        gain,_,count = self.scores(p,mode)
        # Both checkpoints share the same exact-DP order convention.
        return select(self.solve,1,0,p,gain),count


def main():
    assert sha(D/"PROTOCOL_RU.md")==PROTOCOL
    assert read(D/"compiler.json")["model"]==sha(BASE/"model.json.gz")
    m = read(BASE/"manifest.json")["files"]
    pool = read(BASE/"pool.json.gz")
    assert sha(BASE/"pool.json.gz")==m["pool.json.gz"]
    plans = Plans()
    for seed in SEEDS:
        for name in (f"ranks-{seed}.json.gz",f"archive-{seed}.json.gz",f"utility-{seed}.f64.gz"):
            assert sha(BASE/name)==m[name]
        ranks,archive=(read(BASE/f"{name}-{seed}.json.gz") for name in ("ranks","archive"))
        oracle=np.frombuffer(gzip.decompress((BASE/f"utility-{seed}.f64.gz").read_bytes()),dtype="<f8")
        offset = 0
        cases = {}
        for q,r in sorted(pool.items()):
            dense,*orders = ranks[q]
            a = arrays(dict(z=r["x"],offset=r["o"],costs=r["c"],dense=dense,order=orders[0],seed=seed))
            exact = oracle[offset:offset+len(dense)]
            offset += len(dense)
            for cp in range(2):
                p = dict(a,order=np.asarray(orders[cp],dtype=np.int32))
                counts = []
                for mode in range(4):
                    gains,mask,count = plans.scores(p,mode)
                    # Identical IEEE-754 payload for every actually evaluated candidate.
                    assert np.array_equal(gains[mask].view(np.uint64),exact[mask].view(np.uint64))
                    chosen = select(plans.solve,1,cp,p,gains)
                    assert chosen == archive[q][cp][0]
                    counts.append(int(count))
                assert counts[0]==counts[2]==len(dense) and counts[1]==counts[3]
                cases[q,cp] = (p,counts,archive[q][cp][0],r["t"])
        assert offset==len(oracle)
        rng = random.Random(50339+seed)
        measured = {k:[[] for _ in MODES] for k in cases}
        for rep in range(4):
            qorder = list(cases)
            rng.shuffle(qorder)
            for key in qorder:
                p,counts,ref,_ = cases[key]
                modes = list(range(4))
                rng.shuffle(modes)
                for mode in modes:
                    start = perf_counter_ns()
                    selected,n = plans.run(p,mode)
                    ns = perf_counter_ns()-start
                    assert selected==ref and n==counts[mode]
                    if rep: measured[key][mode].append(ns)
        rows = [[q,cp,t,counts,times] for (q,cp),times in measured.items() for _,counts,_,t in [cases[q,cp]]]
        put(D/f"times-{seed}.json.gz",rows)
        print("verified seed",seed,len(rows),flush=True)
    put(D/"run-seal.json",dict(protocol=PROTOCOL,matched=sha(BASE/"manifest.json"),code=sha(Path(__file__)),
        compiler=sha(D/"compiler.json"),files={f"times-{s}.json.gz":sha(D/f"times-{s}.json.gz") for s in SEEDS}))

if __name__ == "__main__":
    main()


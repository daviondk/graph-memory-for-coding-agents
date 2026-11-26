"""Independently recalculate all timing contrasts and run both solvers on the signed inputs."""
from pathlib import Path
from math import isclose
from importlib.util import spec_from_file_location,module_from_spec
import gzip,sys
import numpy as np
from bench_core import D,S,Case,build,h,read,micro
from analyze import calculate

def same(a,b):
    if isinstance(b,dict):return set(a)==set(b) and all(same(a[k],v) for k,v in b.items())
    if isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return isclose(a,b,abs_tol=1e-11,rel_tol=1e-11)
def main():
    floating=D/"float64"
    sys.path.insert(0,str(floating))
    import run as fp
    import score
    assert same(calculate(),read(D/"results.json"))
    assert same(score.compute(),read(floating/"results.json"))
    fs=read(floating/"seal.json");reg=read(D/"forecast-seal.json")
    assert h(floating/"guard.cpp")==fs["code"] and h(D/"core.cpp")==reg["source"]
    direct=build();guard=fp.build()
    assert micro(direct)==reg["exhaustive"] and fp.tiny(guard)==fs["synthetic"]
    ordered=0;old=0
    for seed in (13,17,29,37,41):
        rows=read(S/f"input-{seed}.json.gz")
        weights=np.frombuffer(gzip.decompress((floating/f"weights-{seed}.f64.gz").read_bytes()),dtype="<f8")
        exceptions={(q,g):expect for q,g,expect,pub in reg["different"][str(seed)]}
        offset=0
        for q,v in sorted(rows.items()):
            case=Case(v);size=sum(len(x[2]) for x in case.seq)
            val=weights[offset:offset+size];offset+=size
            assert np.array_equal(np.rint(val*2**32).astype(np.int64),[i for st in case.seq for i in st[3]])
            cols=fp.specialize(case,val)
            for mode in (0,1):
                fp.solve(guard,case,cols,mode)
                assert case.copy()==[st[-1] for st in case.seq]
            for mode in range(4):
                case.run(direct,mode)
                assert case.copy()==[exceptions.get((q,st[0]),st[-1]) for st in case.seq]
            ordered+=len(case.seq)
        assert offset==len(weights);old+=len(exceptions)
    assert ordered==40000 and old==3
    print("Verified 40,000 native binary64 answers, four Q32 plans, three arithmetic differences, synthetic controls and both timing reports.")
if __name__=="__main__":main()

"""Run the self-contained signed example on one CPU."""
from time import perf_counter_ns
_before_import=perf_counter_ns()
import json
import sys
from pathlib import Path
from array import array
import gzip
import ctypes
D=Path(__file__).resolve().parent


def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "raw"
    if mode not in ("native","raw","density","dp"):
        raise SystemExit("Choose native, raw, density or dp")
    if mode=="native":
        t0=perf_counter_ns()
        d=json.loads(gzip.decompress((D/"example-native.json.gz").read_bytes()))
        order,costs=array("i",d["order"]),array("i",d["costs"])
        t1=perf_counter_ns()
        pack=ctypes.CDLL(str(D/"kernels.dll")).pack
        pack.argtypes=[ctypes.c_int]*3+[ctypes.c_void_p]*4
        pack.restype=ctypes.c_int
        t2=perf_counter_ns()
        out=array("i",[0])*len(costs)
        n=pack(len(costs),2048,0,order.buffer_info()[0],costs.buffer_info()[0],None,out.buffer_info()[0])
        result=out[:n].tolist()
        elapsed=perf_counter_ns()-t2
        assert result==d["expected"]
        print(json.dumps(dict(mode=mode,question=d["question"],nodes=result,tokens=sum(costs[i] for i in result),
            import_ns=t0-_before_import,input_ns=t1-t0,model_and_library_ns=t2-t1,
            first_call_ns=elapsed,feature_ns=0,tree_ns=0,selector_ns=elapsed)))
        return
    from runtime import Reader,read,arrays
    t0=perf_counter_ns()
    data=read(D/"example.json.gz")
    pool=arrays(data["pool"])
    t1=perf_counter_ns()
    engine=Reader(learned=mode!="native")
    t2=perf_counter_ns()
    result,parts=engine.run(pool,mode)
    assert result==data["expected"][mode]
    print(json.dumps(dict(mode=mode,question=data["question"],nodes=result,tokens=sum(int(pool["costs"][i]) for i in result),
        import_ns=t0-_before_import,input_ns=t1-t0,model_and_library_ns=t2-t1,first_call_ns=parts[-1],
        feature_ns=parts[0],tree_ns=parts[1],selector_ns=parts[2])))


if __name__=="__main__":
    main()

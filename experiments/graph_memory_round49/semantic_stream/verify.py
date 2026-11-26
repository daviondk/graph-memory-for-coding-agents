"""Verify sealed inputs and reproduce the auxiliary direct-first-fit timing estimate."""
from collections import defaultdict
from importlib.util import spec_from_file_location, module_from_spec
from statistics import median
from run import D,S,digest,load
import numpy as np

def main():
    for name,key in [("stream.cpp","source"),("packets.json.gz","packets"),("timing.json.gz","times"),("PROTOCOL_RU.md","protocol")]:
        assert digest((D/name).read_bytes())==load(D/"forecast-seal.json")[key]
    trials=defaultdict(list)
    for q,rep,mode,t in load(D/"direct-timing.json.gz"):
        trials[q,mode].append((rep,t))
    inp=load(S/"input.json.gz")
    groups={t:i for i,t in enumerate(sorted({r[0] for r in inp.values()}))}
    matrix=np.zeros((len(groups),2))
    for q,(tr,_,_) in inp.items():
        for j,mode in enumerate((101,16)):
            vals=sorted(trials[q,mode])
            assert [r for r,t in vals]==[1,2,3,4,5]
            matrix[groups[tr],j]+=median([t for r,t in vals])
    totals=matrix.sum(axis=0)/1e6
    result=load(D/"direct-results.json")
    assert list(totals)==[result["dense_ms"],result["exact_ms"]]
    assert totals[1]/totals[0]==result["ratio"]
    n=len(groups)
    weights=np.random.default_rng(49172).multinomial(n,np.full(n,1/n),size=10000).astype(float)
    sample=weights@matrix
    assert np.allclose(np.percentile(sample[:,1]/sample[:,0],[2.5,97.5]), result["ci"], rtol=1e-12)
    spec=spec_from_file_location("r49_semantic_grading",D/"analyze.py")
    analyze=module_from_spec(spec)
    spec.loader.exec_module(analyze)
    gold=load(D/"results.json")
    def compare_out(path,data):
        from math import isclose
        def match(a,b):
            if isinstance(b,dict):return set(a)==set(b) and all(match(a[k],v) for k,v in b.items())
            if isinstance(b,list):return len(a)==len(b) and all(match(x,y) for x,y in zip(a,b))
            return isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
        assert match(data,gold)
    analyze.save=compare_out
    analyze.main()
    print("Recomputed 60,000 semantic timing observations, 20,000 direct controls and coverage for 2,000 questions.")
if __name__=="__main__":
    main()

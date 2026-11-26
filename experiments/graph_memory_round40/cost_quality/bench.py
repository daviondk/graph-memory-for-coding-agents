"""Paired timings on all ten thousand signed inputs, one CPU thread."""
from datetime import datetime,timezone
import hashlib
import json
import platform
import subprocess
import sys
from time import perf_counter,perf_counter_ns
from inputs import D,PREV,SEEDS,MODES,REF,arrays,read,sha,save,cases,pool_source
from runtime import Reader,np


def main():
    start=perf_counter()
    codes={n:sha(D/n) for n in ("bench.py","runtime.py","kernels.cpp","kernels.dll","model.json.gz")}
    began=datetime.now(timezone.utc).isoformat()
    inputs=pool_source()
    engine=Reader()
    demo=arrays(read(D/"example.json.gz")["pool"])
    for method in MODES:
        x=engine.features(demo)
        engine.select(demo,method,engine.utility(x))
        engine.run(demo,method)
    stages={}
    for si,seed in enumerate(SEEDS):
        t0=perf_counter()
        receipt=read(PREV/f"test-{seed}-seal.json")
        fam=receipt["rules"]
        p=PREV/f"test-{seed}-packets.json.gz"
        assert sha(p)==receipt["packets"]
        source=read(p)
        prep_start=perf_counter()
        pools=[(q,t,arrays(record)) for q,t,record in cases(seed,inputs)]
        metadata_seconds=perf_counter()-prep_start
        outputs={}
        for ix,(q,tr,pool) in enumerate(pools):
            expected=source[q][1][1][3]
            ref=[expected[fam.index(r)] for r in REF]
            utility=engine.utility(engine.features(pool))
            records=[[] for _ in MODES]
            for rep in range(3):
                values=[[None]*5 for _ in MODES]
                begin=(ix+si+3*rep)%8
                direction=1 if (ix//8+si+rep)%2==0 else -1
                for offset in range(8):
                    slot=(begin+direction*offset)%8
                    j=slot%4
                    if slot<4:
                        before=perf_counter_ns()
                        answer=engine.select(pool,MODES[j],utility if j else None)
                        values[j][0]=perf_counter_ns()-before
                    else:
                        answer,parts=engine.run(pool,MODES[j])
                        values[j][1:]=parts
                    assert answer==ref[j],(seed,q,MODES[j],slot,answer,ref[j])
                for j in range(4):
                    records[j].append(values[j])
            hashes=[hashlib.sha256(json.dumps(a,separators=(",",":")).encode()).hexdigest() for a in ref]
            outputs[q]=[tr,hashes,records]
        assert len(outputs)==2000
        dst=D/f"warm-{seed}.json.gz"
        save(dst,outputs)
        stages[str(seed)]=dict(rows=len(outputs),sha=sha(dst),source=receipt["packets"],metadata_seconds=metadata_seconds,
                               total_seconds=perf_counter()-t0)
        print("checked warm",seed,round(perf_counter()-t0,2),flush=True)
    save(D/"time-seal.json",dict(stages=stages,start_utc=began,elapsed=perf_counter()-start,fields=["cached_selector_ns",
        "features_ns","trees_and_softplus_ns","online_selector_ns","online_total_ns"],methods=MODES,repetitions=3,
        conditions=["cached_utility","numeric_pool"],code=codes,python=platform.python_version(),numpy=np.__version__,
        platform=platform.platform(),protocol=sha(D/"PROTOCOL_RU.md"),inputs=sha(D/"input-seal.json")))


def cold():
    from random import Random
    rng=Random(400240)
    rows=[]
    for rep in range(6):
        methods=list(MODES)
        rng.shuffle(methods)
        for mode in methods:
            t0=perf_counter_ns()
            reply=subprocess.run([sys.executable,"-B",str(D/"demo.py"),mode],capture_output=True,check=True)
            elapsed=perf_counter_ns()-t0
            record=json.loads(reply.stdout)
            assert record["mode"]==mode
            if rep:
                rows.append(dict(wall_ns=elapsed,rep=rep,**record))
    save(D/"cold.json",dict(runs=rows,example=sha(D/"example.json.gz"),native_example=sha(D/"example-native.json.gz"),
                            code=sha(D/"demo.py"),mode="new process each invocation; OS cache ordinary"))
    print("checked cold",len(rows))


if __name__=="__main__":
    if sys.argv[1:]==["cold"]:
        cold()
    else:
        main()

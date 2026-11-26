"""Read-only adapters to the frozen upstream projections, feature weights and signed lists."""
import gzip
import hashlib
import json
from time import perf_counter
from runtime import D,MODES,arrays,read
W=D.parents[1]
R39=W/"graph_memory_round39"
PREV=R39/"hybrid_controls"
SEEDS=(13,17,29,37,41)
REF=("firstfit","graph_value","graph_density","graph_dp")
FEATURES=W.parents[1]/"x20-r33-budget-loss/test.json.gz"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p,obj):
    b=(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix==".gz" else b)


def model():
    global_models=R39/"global_packet/models.json"
    assert sha(global_models)==read(PREV/"test-13-seal.json")["models"]
    corr=read(W/"graph_memory_round35/calibration_scale/models.json")["models"]["oof_3894"]
    ranks={"13":read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"]}
    for seed in SEEDS[1:]:
        ranks[str(seed)]=read(W/f"graph_memory_round21/five_seed/seed-{seed}/calibration.json")["rank"]
    return dict(trees=read(global_models)["models"]["graph"],ranks=ranks,correction=corr)


def pool_source():
    assert sha(FEATURES)==read(W/"graph_memory_round33/budget_loss/test-input.json")["features"]
    return {r["q"]:r for r in read(FEATURES)}


def cases(seed,raw):
    signed=read(PREV/f"test-{seed}-seal.json")
    native=W/f"graph_memory_round22/native_multiseed/official580/seed-{seed}/wo_chunk_adjacency"
    checksum=sha(native/"forecast-seal.json")
    assert checksum in signed["native_seals"].values()
    dense={}
    if seed!=13:
        root=W/f"graph_memory_round21/five_seed/seed-{seed}"
        for tag in read(root/"forecast-seal.json")["receipts"]:
            f=root/tag["file"];assert sha(f)==tag["sha"]
            for r in read(f):
                dense[r["q"]]=r["dense"]
    for tag in read(native/"forecast-seal.json")["receipts"]:
        f=native/tag["file"];assert sha(f)==tag["sha"]
        for r in read(f):
            q=r["q"];z=raw[q];n=len(z["c"])
            assert z["t"]==r["t"] and sorted(r["graph"])==list(range(n))
            yield q,z["t"],dict(z=z["x"],offset=z["o"],costs=z["c"],order=r["graph"],
                dense=dense[q] if dense else list(range(n)),seed=seed)


def build():
    start=perf_counter()
    assert sha(D/"PROTOCOL_RU.md")=="0eacb8536fb4f9128075acc4de4eab937a31d138c890ed8ffc45fa723842c39a"
    export=model()
    save(D/"model.json.gz",export)
    raw=pool_source()
    seed=13
    k=min(raw,key=lambda q:hashlib.sha256(("R40-cpu-example|"+q).encode()).digest())
    for q,t,p in cases(seed,raw):
        if q==k:
            pred=read(PREV/f"test-{seed}-packets.json.gz")[q][1][1][3]
            order=read(PREV/f"test-{seed}-seal.json")["rules"]
            expected={a:pred[order.index(r)] for a,r in zip(MODES,REF)}
            save(D/"example.json.gz",dict(question=q,trajectory=t,pool=p,expected=expected))
            save(D/"example-native.json.gz",dict(question=q,costs=p["costs"],order=p["order"],expected=expected["native"]))
            break
    save(D/"input-seal.json",dict(frozen_protocol=sha(D/"PROTOCOL_RU.md"),sources={str(s):sha(PREV/f"test-{s}-seal.json") for s in SEEDS},
        source_features=sha(FEATURES),example=sha(D/"example.json.gz"),example_native=sha(D/"example-native.json.gz"),model=sha(D/"model.json.gz"),kernel=sha(D/"kernels.dll"),
        kernel_source=sha(D/"kernels.cpp"),export_seconds=perf_counter()-start))


if __name__=="__main__":
    build()

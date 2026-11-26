"""Build blind dev inputs, then call the exact frozen R50 consensus source on those inputs."""
import os
for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[name]="1"
import ctypes as ct
import gzip,sys
from pathlib import Path
import numpy as np

D=Path(__file__).resolve().parent
BASE=D.parent/"matched_reader"
IMPL=D.parent/"packet_consensus"
W=D.parents[1]
sys.path.insert(0,str(BASE))
from common import read,put,sha,SEEDS
from runtime import Reader,arrays
from run_matched import select

def signed_at(folder,name):
    path=folder/name
    assert sha(path)==read(folder/"manifest.json")["files"][name],str(path)
    return path

def make_inputs():
    feat=W.parents[1]/"x20-r33-budget-loss/dev.json.gz"
    tag=read(W/"graph_memory_round33/budget_loss/dev-input.json")
    assert sha(feat)==tag["features"]
    rows=read(feat)
    pool={r["q"]:{"t":r["t"],"c":r["c"]} for r in rows}
    assert len(pool)==580 and len({r["t"] for r in rows})==352 and all(set(r)=={"q","t","x","o","c"} for r in rows)
    law=read(W/"graph_memory_round22/native_multiseed/official580/split.json.gz")
    cal=W/"graph_memory_round35/calibration_scale"
    train=read(cal/"train-inventory.json")
    assert set(train["order"])=={r["q"] for r in law["train"]} and not set(train["order"])&set(pool)
    hgb=read(W/"graph_memory_round39/global_packet/models.json")
    assert hgb["train"]==train["npz"] and hgb["queries"]==3894
    cal_sets={}
    for seed in SEEDS:
        basecal=W/("graph_memory_round20/factor_reader/hash64-weights.json" if seed==13 else f"graph_memory_round21/five_seed/seed-{seed}/calibration.json")
        ids=set(read(basecal)["queries"]);assert len(ids)==101 and ids<=set(train["order"])
        cal_sets[seed]=[len(ids),sha(basecal)]
    model=read(signed_at(BASE,"model.json.gz"))
    assert model["trees"]==hgb["models"]["graph"]
    rate=Reader();fn=rate.lib.packet
    fn.argtypes=[ct.c_int]*3+[ct.c_void_p]*4;fn.restype=ct.c_int
    put(D/"pool.json.gz",pool)
    files=["pool.json.gz"];source={}
    for seed in SEEDS:
        file=D/f"native-{seed}.json.gz";seal=read(D/f"native-{seed}-seal.json")
        assert sha(file)==seal["result"]
        nk=read(file)
        assert set(nk)==set(pool)
        rankings={};prior={};predicted={}
        for r in rows:
            q=r["q"];rank=nk[q];n=len(r["c"])
            dense=list(range(n)) if seed==13 else rank["dense"]
            assert all(sorted(x)==list(range(n)) for x in (dense,rank["recall"],rank["full"]))
            cfg=arrays(dict(z=r["x"],offset=r["o"],costs=r["c"],dense=dense,order=rank["recall"],seed=seed))
            u=rate.utility(rate.features(cfg))
            c1=dict(cfg,order=np.asarray(rank["full"],dtype=np.int32))
            b0=select(fn,0,0,cfg,u);b1=select(fn,0,1,c1,u)
            rankings[q]=[dense,rank["recall"],rank["full"]]
            prior[q]=[[b0],[b1]]
            predicted[q]=u.astype("<f8",copy=False).tobytes()
        a,b,c=f"ranks-{seed}.json.gz",f"archive-{seed}.json.gz",f"utility-{seed}.f64.gz"
        put(D/a,rankings);put(D/b,prior)
        (D/c).write_bytes(gzip.compress(b"".join(predicted[q] for q in sorted(pool)),mtime=0,compresslevel=4))
        files.extend([a,b,c]);source[seed]=sha(file)
    put(D/"input-seal.json",dict(files={k:sha(D/k) for k in files},native=source,rank_calibration=cal_sets,rows=len(rows),split=[len(law[k]) for k in ["train","dev","test"]],train=sha(cal/"train-inventory.json"),model=sha(BASE/"model.json.gz"),trees=sha(W/"graph_memory_round39/global_packet/models.json"),features=sha(feat),source=sha(Path(__file__))))

def aggregate():
    import importlib.util
    target=signed_at(IMPL,"run.py")
    spec=importlib.util.spec_from_file_location("unchanged_ensemble",target)
    ensemble=importlib.util.module_from_spec(spec);spec.loader.exec_module(ensemble)
    inputs=read(D/"input-seal.json")["files"]
    def getdata(name):
        p=D/name;assert sha(p)==inputs[name];return p
    class OutputFolder:
        def __truediv__(self,name):
            if name=="PROTOCOL_RU.md":return signed_at(IMPL,name)
            if name=="forecast-seal.json":return D/"implementation-seal.json"
            return D/name
    ensemble.D=OutputFolder()
    ensemble.signed=getdata
    ensemble.main()
    p=D/"packets.json.gz";assert sha(p)==read(D/"implementation-seal.json")["forecasts"]
    put(D/"forecast-seal.json",dict(forecasts=sha(p),protocol=sha(D/"PROTOCOL_RU.md"),packet_source=sha(target),inputs=sha(D/"input-seal.json"),source=sha(Path(__file__)),count=580))

if __name__=="__main__":
    make_inputs()
    aggregate()


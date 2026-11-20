"""Rerun the fixed graph operations with the high-resolution per-thread cycle counter on Windows."""
import ctypes
from ctypes import wintypes
import gc,gzip,json,statistics,tracemalloc,hashlib
from collections import Counter,defaultdict
import numpy as np
import incremental as impl

D=impl.D
kernel=ctypes.WinDLL("kernel32",use_last_error=True)
kernel.GetCurrentThread.restype=wintypes.HANDLE
kernel.QueryThreadCycleTime.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_ulonglong)]
kernel.QueryThreadCycleTime.restype=wintypes.BOOL
handle=kernel.GetCurrentThread()
def cycles():
    v=ctypes.c_ulonglong()
    if not kernel.QueryThreadCycleTime(handle,ctypes.byref(v)):raise ctypes.WinError(ctypes.get_last_error())
    return v.value
impl.process_time_ns=cycles
def mem(texts):
    nodes=[impl.record(t) for t in texts]
    def measure(base):
        gc.collect();tracemalloc.start()
        if base:view=impl.encode(texts)
        else:
            g=impl.EventGraph()
            for n in nodes:g.add(n)
            view=g.view()
        current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        return [current,peak]
    return {"rebuild":measure(True),"insert":measure(False)}
def main():
    read=lambda p:json.loads(p.read_bytes())
    src=D.parent/"encoder"/"blind.jsonl.gz"
    hashes={p.name:impl.hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),D/"INCREMENTAL_TIMER_RU.md",D/"incremental_lock.json",src]}
    (D/"cycle_lock.json").write_text(json.dumps(hashes),encoding="utf8")
    rows=list(map(json.loads,gzip.open(src,"rt",encoding="utf8")));groups=defaultdict(list)
    for r in rows:groups[r["panel"]].append(r)
    mem_ids={(r["panel"],r["idx"]) for v in groups.values() for r in sorted(v,key=lambda r:hashlib.sha256(("r4incmem|"+str(r["idx"])).encode()).digest())[:8]}
    logs=[]
    for r in rows:
        texts=r["candidates"]; pair=(r["panel"],r["idx"]); m=mem(texts) if pair in mem_ids else {}
        orders={"listed":texts,"shuffled":[t for _,t in sorted(enumerate(texts),key=lambda z:hashlib.sha256(("r4inc|"+str(z[0])+z[1]).encode()).digest())]}
        for order,seq in orders.items():
            ms=[impl.benchmark(r,seq) for _ in range(3)];cycles_by_method={k:statistics.median(a["times_ns"][k] for a in ms) for k in ms[0]["times_ns"]}
            logs.append({"id":pair,"project":r["project"],"order":order,"cycles":cycles_by_method,"raw_cycle_pairs":[a["times_ns"] for a in ms],"verified_checkpoints_per_pass":len(seq),"memory":m if order=="listed" else {}})
    (D/"cycle_items.json.gz").write_bytes(gzip.compress(json.dumps(logs,separators=(",",":")).encode(),mtime=0))
    summary={}
    for order in ("listed","shuffled"):
        selected=[r for r in logs if r["order"]==order];groups=defaultdict(list)
        for r in selected:groups[r["project"]].append(r)
        methods=("each","add_each","final","add_final")
        mat=np.array([[sum(r["cycles"][k] for r in v) for k in methods] for v in groups.values()])
        ds=mat[np.random.default_rng(12511).integers(len(mat),size=(10000,len(mat)))].sum(axis=1);s=mat.sum(axis=0)
        summary[order]={"n":len(selected),"distinct_checkpoints":sum(r["verified_checkpoints_per_pass"] for r in selected),"repeat_speedup":s[0]/s[1],"repeat_ci":np.quantile(ds[:,0]/ds[:,1],[.025,.975]).tolist(),"single_new_to_base":s[3]/s[2],"single_ci":np.quantile(ds[:,3]/ds[:,2],[.025,.975]).tolist(),"minimum_observed_cycles":min(min(r["cycles"].values()) for r in selected)}
    ms=[r["memory"] for r in logs if r["memory"]]
    summary["memory"]={"n":len(ms),"median_live_bytes":{k:statistics.median(r[k][0] for r in ms) for k in ("rebuild","insert")},"median_peak_bytes":{k:statistics.median(r[k][1] for r in ms) for k in ("rebuild","insert")}}
    (D/"cycle_results.json").write_text(json.dumps(summary,indent=2),encoding="utf8");print(summary)
if __name__=="__main__":
    from pathlib import Path
    main()


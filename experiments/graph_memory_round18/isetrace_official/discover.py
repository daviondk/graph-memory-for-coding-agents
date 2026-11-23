"""Recover v7 test IDs by applying official functions to every released source trajectory."""
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import sys
import time

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]/"graph_memory_round17/isetrace"
sys.path.insert(0,str(BASE))
import pilot
from graph_memory.datasets.splits import sample_split
N=pilot.native
RAW=pilot.CACHE/"trajectories"
def write(name,obj):
    dst=ROOT/name
    data=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()+b"\n"
    if name.endswith(".gz"):data=gzip.compress(data,mtime=0)
    if dst.exists():assert dst.read_bytes()==data,name
    else:
        tmp=dst.with_suffix(dst.suffix+".tmp")
        tmp.write_bytes(data);tmp.replace(dst)
def load(name):
    raw=(ROOT/name).read_bytes();return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)
def all_inputs():
    lock=load("source-lock.json")
    assert len(lock)==11
    for item in lock:assert pilot.sha(pilot.CACHE/item["path"])==item["sha256"],item["path"]
def recover():
    all_inputs()
    summary=N.ISETraceBenchmarkSummary()
    queries=N._read_queries(pilot.Q,strict=False,summary=summary)
    meta=N._read_authoring_query_metadata(pilot.META,query_ids={q.id for q in queries},summary=summary)
    # Pass-through instrumentation preserves the canonical reader, its yielded objects and order.
    saved=N.iter_canonical_trajectories
    def logged(*args,**kwargs):
        t=time.monotonic()
        for j,record in enumerate(saved(*args,**kwargs),1):
            if j%1000==0:print("canonical",j,round(time.monotonic()-t,1),"seconds",flush=True)
            yield record
    N.iter_canonical_trajectories=logged
    try:matches=N._match_query_contexts(RAW,examples=queries,source_revision=pilot.RAW[1],strict=False,summary=summary)
    finally:N.iter_canonical_trajectories=saved
    valid=[q for q in queries if q.id in matches]
    group=N.allocate_trajectory_splits([matches[q.id][0].trajectory_id for q in valid],split_counts={"train":2410,"dev":352,"test":1207},split_seed=13)
    selected=sample_split([q for q in valid if matches[q.id][0].trajectory_id in group["test"]],count=None,seed=13,offset=0)
    rows=[];gold={};modes=Counter()
    for q in selected:
        tr,mapping=matches[q.id]
        assert meta[q.id].trajectory_id==tr.trajectory_id
        m=meta[q.id].memory_mode;modes[m]+=1
        rows.append({"query_id":q.id,"trajectory_id":tr.trajectory_id,"memory_mode":m})
        gold[q.id]=[v.model_dump() for v in N._resolve_gold_spans(q,mapping)]
    groups={s:{"queries":sum(matches[q.id][0].trajectory_id in ids for q in valid),"trajectories":len(ids)} for s,ids in group.items()}
    report={"native_match":dict(summary),"resolved":len(valid),"dropped_queries":sorted({q.id for q in queries}-set(matches)),
            "groups":groups,"modes":dict(modes),"official_signature_match":len(rows)==2000 and len({q['trajectory_id'] for q in rows})==1207 and dict(modes)=={"direct_recall":641,"linked_recall":906,"multi_fact_recall":453}}
    write("cohort.json",rows);write("gold-spans.json.gz",gold);write("split-verification.json",report)
    print(groups,modes,"shape_match",report["official_signature_match"],flush=True)
if __name__=="__main__":recover()

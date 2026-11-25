"""Evaluate matched chronological prefixes without disclosing trajectory payloads."""
from __future__ import annotations
import collections
import gzip
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from time import perf_counter
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[key]="1"
import numpy as np

D=Path(__file__).resolve().parent
R20=D.parents[1]/"graph_memory_round20"
sys.path.insert(0,str(R20/"residual_graph"))
import setup_graph as env
from graph_memory.graphs.provenance import FEEDS_EDGE,build_provenance_graph
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
from stream import FeedIndex

def save(p,obj):
    raw=(json.dumps(obj,separators=(",",":"),sort_keys=True,allow_nan=False)+"\n").encode()
    if p.suffix==".gz":raw=gzip.compress(raw,mtime=0)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(raw);os.replace(tmp,p)


def edge_hash(edges):
    return hashlib.sha256(json.dumps(sorted(edges),separators=(",",":")).encode()).hexdigest()


def reference(tr):
    graph=build_provenance_graph(tr)
    return {(e.source.removeprefix("output:"),e.target.removeprefix("call:")) for e in graph.edges if e.relation==FEEDS_EDGE}


def cohort():
    rows=env.load(env.TR/"split.json.gz")["test"]
    names=sorted({r["t"] for r in rows},key=lambda t:hashlib.sha256(("incremental-feeds-v1"+t).encode()).digest())[:96]
    assert len(names)==96
    plan={"trajectories":names,"split":env.pilot.sha(env.TR/"split.json.gz"),"protocol":env.pilot.sha(D/"PROTOCOL_RU.md"),
          "source_code":env.pilot.sha(D/"stream.py"),"evaluator":env.pilot.sha(D/"evaluate.py")}
    dest=D/"plan.json"
    if dest.exists():assert json.loads(dest.read_bytes())==plan
    else:save(dest,plan)
    return set(names)


def trace(tr):
    boundaries=[];pending=set()
    for j,e in enumerate(tr.events):
        if e.event_type=="tool_call":pending.add(e.call_id)
        if e.event_type=="tool_output":
            pending.remove(e.call_id)
            if not pending:boundaries.append(j)
    assert not pending and boundaries
    cuts=sorted({boundaries[math.ceil(len(boundaries)*k/4)-1] for k in range(1,5)})
    # This comparator has retrospective access. The index below sees only one new event per call.
    final=reference(tr)
    live=FeedIndex();calls=set();outputs=set();records=[];events=[]
    peaks=collections.Counter()
    for j,e in enumerate(tr.events):
        if e.event_type=="tool_call":calls.add(e.call_id)
        if e.event_type=="tool_output":outputs.add(e.call_id)
        before=(live.adds,live.removes,live.witness_deletions,live.preserved_multiple)
        live.consume(e)
        after=(live.adds,live.removes,live.witness_deletions,live.preserved_multiple)
        if before!=after:events.append([j,*[y-x for x,y in zip(before,after)]])
        if e.event_type!="message":
            now=live.state_size()
            for key,val in now.items():peaks[key]=max(peaks[key],val)
        if j not in cuts:continue
        prefix=tr.model_copy(update={"events":tr.events[:j+1],"source_total_steps":j+1,"final_response":"","source_metadata":None})
        gold=reference(prefix)
        hindsight={(a,b) for a,b in final if a in outputs and b in calls}
        methods={"counted":set(live.support), "append":live.ever,"retrospective":hindsight}
        outcomes={}
        for name,edges in methods.items():
            outcomes[name]={"tp":len(gold&edges),"fp":len(edges-gold),"fn":len(gold-edges),"sha":edge_hash(edges)}
        records.append(dict(index=j,last=j==cuts[-1],calls=len(calls),gold=len(gold),sha=edge_hash(gold),arms=outcomes))
    return {"t":tr.trajectory_id,"n_events":len(tr.events),"n_closed":len(boundaries),"records":records,
            "events":events,"peaks":dict(peaks),"adds":live.adds,"removes":live.removes,"ambiguities":live.ambiguities,
            "witness_deletions":live.witness_deletions,"preserved_multi":live.preserved_multiple}


def main():
    selected=cohort();cohort_rows=[]
    locks={row["path"]:row["sha256"] for row in env.load(env.R18/"isetrace_official/source-lock.json")}
    for k in range(8):
        path=env.RAW/f"trajectories-{k:05d}.jsonl"
        assert env.pilot.sha(path)==locks["trajectories/"+path.name]
        for raw,obj in env.pilot.stream(path):
            if obj["session_id"] not in selected:continue
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=env.pilot.RAW[1])
            rec=trace(tr);rec["source_sha256"]=hashlib.sha256(raw).hexdigest();cohort_rows.append(rec)
        print("shard",k,"trajectories",len(cohort_rows),flush=True)
    assert {r["t"] for r in cohort_rows}==selected and len(cohort_rows)==len(selected)
    save(D/"prefix-outcomes.json.gz",cohort_rows)
    summary={}
    for name in ("counted","append","retrospective"):
        for final in (False,True):
            groups=[];totals=collections.Counter()
            for traj in cohort_rows:
                rd=[r["arms"][name] for r in traj["records"] if r["last"]==final]
                groups.append((len(rd),sum(bool(r["fp"]+r["fn"]) for r in rd)))
                for r in rd:
                    for k in ("tp","fp","fn"):totals[k]+=r[k]
            arr=np.array(groups);rng=np.random.default_rng(21014)
            sampled=arr[rng.integers(0,len(arr),size=(10000,len(arr)))].sum(axis=1)
            n,w=arr.sum(axis=0)
            summary[name+("/final" if final else "/intermediate")]=dict(n=int(n),mismatched=int(w),fraction=float(w/n),
                ci=np.quantile(sampled[:,1]/sampled[:,0],[.025,.975]).tolist(),**totals)
    summ={k:sum(r[k] for r in cohort_rows) for k in ("adds","removes","ambiguities","witness_deletions","preserved_multi","n_events")}
    save(D/"results.json",{"cohort":len(selected),"prefixes":sum(len(r["records"]) for r in cohort_rows),"summary":summary,
        "events":summ,"with_removals":sum(r["removes"]>0 for r in cohort_rows),"plan":env.pilot.sha(D/"plan.json"),
        "outcomes":env.pilot.sha(D/"prefix-outcomes.json.gz"),"maximum_resident":{k:max(r["peaks"].get(k,0) for r in cohort_rows)
        for k in ("live_witnesses","known_values","unique_values","live_edges")}})
    print(summary,summ,flush=True)


if __name__=="__main__":main()

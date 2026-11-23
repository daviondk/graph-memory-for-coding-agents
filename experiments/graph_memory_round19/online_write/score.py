"""Score sealed forecasts. The official span scorer sees labels here for the first time."""
import collections
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
from predict import HERE, RUNTIME, digest, dump
sys.path.insert(0, str(RUNTIME / "upstream"))
from graph_memory.evaluation.span_metrics import span_metrics_at
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.trajectories import SourceSpan

GOLD = HERE.parent.parent / "graph_memory_round18/isetrace_official/gold-spans.json.gz"
NBOOT = 10000

def independent(gold, spans):
    # Blocks from one stream are disjoint; gold can overlap. Sweep only gold addresses.
    total = covered = 0
    merged = collections.defaultdict(list)
    for g in sorted(gold, key=lambda x:(x.event_id,x.json_pointer,x.char_start,x.char_end)):
        ranges = merged[g.event_id,g.json_pointer]
        if ranges and ranges[-1][1] >= g.char_start:
            ranges[-1][1] = max(ranges[-1][1],g.char_end)
        else:
            ranges.append([g.char_start,g.char_end])
    for pairs in merged.values():
        total += sum(b-a for a,b in pairs)
    for s in spans:
        covered += sum(max(0,min(b,s.char_end)-max(a,s.char_start))
                       for a,b in merged.get((s.event_id,s.json_pointer),[]))
    return covered == total, covered / total

def take(nodes, gold, check):
    m = span_metrics_at(tuple(nodes),gold,len(nodes))
    if check:
        fs, cov = independent(gold, [n.source_spans[0] for n in nodes])
        assert fs == m.full_support and abs(cov-m.coverage) < 1e-12
    return [int(m.full_support), m.coverage, m.density]

def ci(rows, arms, metric):
    # Resample trajectories with replacement; retain every question for each sampled cluster.
    grouped = collections.defaultdict(list)
    for r in rows:
        grouped[r["t"]].append(r["a"][arms[0]][metric]-r["a"][arms[1]][metric])
    n = np.array([len(x) for x in grouped.values()])
    effects = np.array([sum(x) for x in grouped.values()])
    rng = np.random.default_rng(13)
    reps = []
    for _ in range(NBOOT//100):
        idx = rng.integers(0,len(n),(100,len(n)))
        reps.extend(np.sum(effects[idx],axis=1)/np.sum(n[idx],axis=1))
    return [float(effects.sum()/n.sum()), *map(float,np.quantile(reps,[.025,.975]))]

def main():
    seal = json.loads((HERE/"forecast-lock.json").read_bytes())
    assert digest(HERE/"predict.py") == seal["predict"]
    assert digest(HERE/"PROTOCOL_RU.md") == seal["protocol"]
    assert len(seal["forecasts"]) == 8
    for file, expected in seal["forecasts"].items():
        assert digest(HERE/file) == expected
    with gzip.open(GOLD,"rb") as f:
        truth = {q:tuple(SourceSpan(**s) for s in gs) for q,gs in json.load(f).items()}
    rows, trajectories, audits = [], [], 0
    for file in sorted(seal["forecasts"]):
        with gzip.open(HERE/file,"rt",encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                check = int(hashlib.sha256(r["t"].encode()).hexdigest()[:8],16) % 16 == 0
                nodes = []
                blocks, addresses = r["blocks"],r["addresses"]
                for i,(e,a,b,c,_) in enumerate(blocks):
                    eid,pointer = addresses[e]
                    s = SourceSpan(event_id=eid,json_pointer=pointer,char_start=a,char_end=b)
                    nodes.append(RankedNodeRecord(node_id=str(i),score=0,source_spans=(s,),token_count=c))
                qrows, costs = {}, {}
                for pol,(keep,reads) in r["arms"].items():
                    keep = list(range(len(nodes))) if keep is None else keep
                    assert len(set(keep)) == len(keep)
                    kept = [nodes[i] for i in keep]
                    all_cost = sum(n.token_count for n in kept)
                    if pol != "all": assert all_cost <= int(pol.split("/")[1])
                    meta = [[blocks[i][0],blocks[i][1],blocks[i][2]] for i in keep]
                    address_table = {e:addresses[e] for e in sorted({x[0] for x in meta})}
                    costs[pol] = [all_cost,sum(blocks[i][4] for i in keep),len(dump([address_table,meta]).encode()),
                                  len(keep),len(address_table)]
                    for qid,sel in reads.items():
                        assert len(set(sel)) == len(sel) and set(sel).issubset(keep)
                        selected = [nodes[i] for i in sel]
                        read_cost = sum(n.token_count for n in selected)
                        assert read_cost <= 2048
                        stored, read = take(kept,truth[qid],check),take(selected,truth[qid],check)
                        assert read[0] <= stored[0] and read[1] <= stored[1]+1e-12
                        qrows.setdefault(qid,{})[pol] = stored+read+[read_cost]
                        audits += 2*check
                trajectories.append(dict(t=r["t"],cost=costs,unmatched=r["unmatched"]))
                rows.extend(dict(t=r["t"],q=q,a=a) for q,a in qrows.items())
    assert len(trajectories)==1207 and len({r["t"] for r in trajectories})==1207
    assert set(r["q"] for r in rows)==truth.keys() and len(rows)==2000
    policies = sorted(rows[0]["a"])
    assert all(sorted(r["a"])==policies for r in rows)
    summary = {}
    for pol in policies:
        x = np.array([r["a"][pol] for r in rows])
        c = np.array([r["cost"][pol] for r in trajectories])
        summary[pol] = dict(write_count=int(x[:,0].sum()),read_count=int(x[:,3].sum()),metrics=x.mean(axis=0).tolist(),
                            costs_per_trajectory=c.mean(axis=0).tolist())
    contrasts = {f"{a}-{b}/{metric}":ci(rows,(a,b),i)
                 for a,b in [("head/8192","fifo/8192"),("head/8192","hash/8192"),
                             ("ends/8192","head/8192"),("output_head/8192","head/8192")]
                 for i,metric in [(0,"write_FS"),(3,"read_FS"),(1,"write_coverage"),(4,"read_coverage")]}
    totals = {cap:sum(r["cost"]["all"][0]>cap for r in trajectories) for cap in (4096,8192,16384)}
    out = dict(n=len(rows),trajectories=len(trajectories),gold_sha256=digest(GOLD),independently_checked=audits,
               unmatched_field_count=sum(r["unmatched"] for r in trajectories),over_budget_trajectories=totals,
               outcome_columns=["write_FS","write_coverage","write_density","read_FS","read_coverage","read_density","read_tokens"],
               cost_columns=["stored_tokens","payload_utf8_bytes","address_JSON_bytes","blocks","events"],
               summary=summary,contrasts=contrasts)
    for file, data in (("outcomes.json.gz",rows),("storage.json.gz",trajectories)):
        (HERE/file).write_bytes(gzip.compress(dump(data).encode(),mtime=0))
    (HERE/"results.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    for k,v in summary.items():
        print(k, v["write_count"], v["read_count"])
    print("CIs", contrasts, "audited",audits)

if __name__ == "__main__":
    main()


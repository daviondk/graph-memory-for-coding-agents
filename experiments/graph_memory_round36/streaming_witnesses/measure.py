"""Compare complete logical edge identities against the canonical support index, event by event."""
import hashlib
import json
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
for var in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):os.environ[var]="1"
import numpy as np
D=Path(__file__).resolve().parent
SRC=D.parent/"materialized_append"
sys.path.insert(0,str(SRC))
import materialize as ref
from reader import HistoricalFeeds

def work(shard):
    index=ref.l.ref.graph_index()
    graphdata=ref.load(SRC/f"graphs-{shard}.json.gz")
    p=ref.l.env.RAW/f"trajectories-{shard:05d}.jsonl"
    assert ref.sha(p)==ref.load(ref.R34/"plan.json")["raw"][p.name]
    out={}
    for line,obj in ref.l.env.pilot.stream(p):
        t=obj["session_id"]
        if t not in graphdata:continue
        path,dig=index[t];assert ref.sha(path)==dig
        record=ref.load(path);assert hashlib.sha256(line).hexdigest()==record["raw_source"]
        chunks=Counter(node["attributes"]["call_id"] for node in record["g"]["nodes"] if node["kind"]==ref.l.ref.OUTPUT_CHUNK_NODE)
        events=ref.l.parent.adapt_isetrace_record(ref.l.parent.parse_isetrace_record(obj),source_revision=ref.l.env.pilot.RAW[1]).events
        cuts=ref.l.parent.cuts_for(events)
        by_cut={j:[] for j in cuts}
        for tag,j in zip((25,50,75,100),cuts):by_cut[j].append(str(tag))
        previous=ref.l.FeedIndex()
        compact=HistoricalFeeds()
        seen,visible=set(),set()
        stats={"peak_old":0,"peak_open":0,"sum_old":0,"sum_open":0,"steps":0,"checked_cuts":0,"max_open_calls":0,
               "checked_live_pairs":0}
        for step,event in enumerate(events):
            if event.event_type not in ("tool_call","tool_output"):continue
            output=(event.event_type=="tool_output")
            nonempty=output and chunks[event.call_id]>0
            previous.consume(event)
            compact.consume(event,has_output_chunks=nonempty)
            if nonempty:visible.add(event.call_id)
            seen.update((a,b) for a,b in previous.support if a in visible and b in visible)
            assert seen==compact.observed_pairs and visible==compact.visible_outputs
            assert previous.values.keys()==compact.producer.keys()
            assert all((previous.values[k] is None)==(v is None) and
                       (v is None or v==(previous.values[k].source,previous.values[k].position)) for k,v in compact.producer.items())
            old=sum(len(e.readers) for e in previous.values.values() if e is not None)
            current=compact.pending_references()
            stats["max_open_calls"]=max(stats["max_open_calls"],len(compact.open_calls))
            stats["steps"]+=1
            stats["checked_live_pairs"]+=len(seen)
            stats["sum_old"]+=old;stats["sum_open"]+=current
            stats["peak_old"]=max(old,stats["peak_old"]);stats["peak_open"]=max(current,stats["peak_open"])
            for cut in by_cut.get(step,()):
                expect=graphdata[t]["states"][cut]
                assert len(seen)==expect["logical_pairs"]["M"] and sum(chunks[a]*chunks[b] for a,b in seen)==expect["material"]
                stats["checked_cuts"]+=1
        assert not compact.open_calls and stats["checked_cuts"]==4
        stats["terminal_old"]=old;stats["terminal_open"]=current;stats["pairs_final"]=len(seen)
        out[t]=stats
    assert set(out)==set(graphdata)
    f=D/f"histories-{shard}.json.gz";ref.put(f,out)
    return f.name,ref.sha(f)

def main():
    assert ref.sha(SRC/"manifest.json")=="33cfd9168b28c67b8924f00a5b38abb1dba7a133ba282d9449ba624cb74c77b2"
    ref.put(D/"plan.json",dict(source=ref.sha(SRC/"manifest.json"),code=ref.sha(Path(__file__)),reader=ref.sha(D/"reader.py"),protocol=ref.sha(D/"PROTOCOL_RU.md")))
    with ProcessPoolExecutor(2) as pool: parts=dict(pool.map(work,range(8)))
    all_rows={}
    for path,h in parts.items():
        f=D/path;assert ref.sha(f)==h;all_rows.update(ref.load(f))
    assert len(all_rows)==1207
    keys=list(next(iter(all_rows.values())))
    values={k:np.asarray([all_rows[t][k] for t in sorted(all_rows)]) for k in keys}
    a,b=values["peak_old"],values["peak_open"]
    rng=np.random.default_rng(360407);diff=[];ratio=[]
    for _ in range(100):
        ix=rng.integers(1207,size=(100,1207));diff.extend((a[ix]-b[ix]).mean(1));ratio.extend(1-b[ix].sum(1)/a[ix].sum(1))
    ref.put(D/"results.json",dict(histories=len(all_rows),totals={k:int(x.sum()) for k,x in values.items()},
        peak_mean=[a.mean(),b.mean()],peak_median=[np.median(a),np.median(b)],
        peak_reduction=(a-b).mean(),peak_reduction_ci=np.quantile(diff,[.025,.975]).tolist(),
        peak_fraction=1-b.sum()/a.sum(),peak_fraction_ci=np.quantile(ratio,[.025,.975]).tolist(),
        peak_direction=[int((a>b).sum()),int((a==b).sum()),int((a<b).sum())],
        event_integral_fraction=1-values["sum_open"].sum()/values["sum_old"].sum(),
        parallel_histories=int((values["max_open_calls"]>1).sum()),files=parts,plan=ref.sha(D/"plan.json")))
if __name__=="__main__":main()


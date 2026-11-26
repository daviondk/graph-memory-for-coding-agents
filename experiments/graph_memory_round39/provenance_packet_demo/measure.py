"""Check frozen predictions and measure real selection, recording every query and timing."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
from time import perf_counter_ns
from reader import D,Reader,Evaluator

SCENARIOS=("main","small","large","exclude")

def save(path,value):
    raw=(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)

def measure(out):
    out.mkdir(parents=True,exist_ok=True)
    if any((out/p).exists() for p in ('observations.json.gz','results.json')):raise ValueError("use a fresh output directory")
    reader=Reader();reference=json.loads((D/'reference.json').read_bytes());queries=reader.queries()
    assert len(queries)==len(reference)==40 and [r[1] for r in reader.db.execute('PRAGMA database_list')]==['main']
    chosen={};timings={}
    for i,q in enumerate(queries):
        sources=reader.sources(q); source=sources[0]['id']; opts={'main':(2048,None),'small':(1024,None),'large':(3072,None),'exclude':(2048,source)}
        arm={s:reader.choose(q,*v) for s,v in opts.items()};times={s:[] for s in opts}
        for rep in range(5):
            offset=(i+rep)%4
            for s in SCENARIOS[offset:]+SCENARIOS[:offset]:
                begin=perf_counter_ns();value=reader.choose(q,*opts[s]);elapsed=perf_counter_ns()-begin
                assert value==arm[s];times[s].append(elapsed)
        ref=reference[q];assert arm['main']['ids']==ref['ids'] and arm['main']['tokens']==ref['official'][2],q
        for s,result in arm.items():
            assert len(set(result['ids']))==len(result['ids']) and result['tokens']<=result['budget']
            if s=='exclude':assert all(span['source']!=source for item in reader.explain(result) for span in item['spans'])
        chosen[q]=arm;timings[q]=times
    grader=Evaluator();rows={}; summaries={}
    for q,arms in chosen.items():
        base=set(arms['main']['ids']);outcomes={}
        for s,result in arms.items():
            ev=grader.evaluate(reader,result); ids=set(result['ids'])
            outcomes[s]=dict(result,**ev,added=sorted(ids-base),removed=sorted(base-ids),elapsed_ns=timings[q][s])
        row=outcomes['main'];ref=reference[q]['official'];assert row['full_support']==ref[0] and abs(row['coverage']-ref[1])<=1e-12 and len(row['ids'])==ref[3]
        rows[q]=outcomes
    for s in SCENARIOS:
        batch=[v[s] for v in rows.values()];ts=sorted(t for v in batch for t in v['elapsed_ns']);mean=statistics.mean
        summaries[s]=dict(queries=len(batch),calls=len(ts),p50_us=statistics.median(ts)/1000,p95_us=ts[math.ceil(.95*len(ts))-1]/1000,mean_tokens=mean(v['tokens'] for v in batch),total_tokens=sum(v['tokens'] for v in batch),mean_selected=mean(len(v['ids']) for v in batch),full_support=sum(v['full_support'] for v in batch),mean_coverage=mean(v['coverage'] for v in batch),changed_sets=sum(bool(v['added'] or v['removed']) for v in batch),mean_added=mean(len(v['added']) for v in batch),mean_removed=mean(len(v['removed']) for v in batch))
    save(out/'observations.json.gz',rows);save(out/'results.json',dict(queries=40,seed=13,iden_order=40,iden_official_full_coverage_cost_count=40,sqlite=sqlite3.sqlite_version,python=sys.version.split()[0],platform=platform.platform(),processor=platform.processor(),reader_sha256=hashlib.sha256((D/'reader.py').read_bytes()).hexdigest(),arms=summaries));print(summaries,flush=True)
if __name__=='__main__':measure(Path(sys.argv[1]) if len(sys.argv)>1 else D)

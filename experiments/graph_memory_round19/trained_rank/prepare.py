"""Project train and dev without ever loading the held-out evidence labels."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,sys
ROOT=Path(__file__).resolve().parent
R18=ROOT.parents[1]/'graph_memory_round18'
sys.path.insert(0,str(R18/'isetrace_e5'))
from project import load,put,pilot,OFF
from discover import N,sample_split,RAW
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
from graph_memory.trajectories import source_spans_overlap
RUN=Path('D:/CodexResearch/x20-isetrace-trained')
def assignment():
    valid_drop=set(load(OFF/'split-verification.json')['dropped_queries'])
    meta={m['query_id']:m['trajectory_id'] for _,m in pilot.stream(pilot.META)}
    qs=[q['id'] for _,q in pilot.stream(pilot.Q) if q['id'] not in valid_drop]
    groups=N.allocate_trajectory_splits([meta[q] for q in qs],split_counts={'train':2410,'dev':352,'test':1207},split_seed=13)
    result={k:[dict(q=q,t=meta[q]) for q in sample_split([q for q in qs if meta[q] in ids],count=500 if k=='dev' else None,seed=13,offset=0)] for k,ids in groups.items()}
    assert set(r['q'] for r in result['test'])==set(r['query_id'] for r in load(OFF/'cohort.json'))
    assert {k:len(v) for k,v in result.items()}=={'train':3894,'dev':500,'test':2000}
    assert not (groups['train']&groups['dev'] or groups['train']&groups['test'] or groups['test']&groups['dev'])
    put(ROOT/'split.json.gz',result)
    put(ROOT/'protocol-seal.json',{p.name:pilot.sha(p) for p in [ROOT/'PROTOCOL_RU.md',ROOT/'prepare.py',ROOT/'split.json.gz',OFF/'source-lock.json']})
def shard(i):
    trd=load(ROOT/'split.json.gz');by=defaultdict(dict)
    for split in ['train','dev']:
        for r in trd[split]:by[r['t']][r['q']]=split
    keep={q for x in by.values() for q in x}
    parsed=N._read_queries(pilot.Q,strict=False,summary=N.ISETraceBenchmarkSummary())
    examples={q.id:q for q in parsed if q.id in keep}
    source=RAW/f'trajectories-{i:05d}.jsonl';locks={r['path']:r['sha256'] for r in load(OFF/'source-lock.json')}
    assert pilot.sha(source)==locks['trajectories/'+source.name]
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    n=0
    for raw,obj in pilot.stream(source):
        t=obj['session_id']
        if t not in by:continue
        tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=pilot.RAW[1])
        g=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64))
        pool=pilot.native.provenance_unit_candidates(g)
        qq=[]
        for q,which in by[t].items():
            ex=examples[q];mapping=N._match_task_text(ex,tr);assert mapping is not None
            gs=N._resolve_gold_spans(ex,mapping)
            ids=[c.item_id for c in pool if any(source_spans_overlap(s,sp) for s in c.source_spans for sp in gs)]
            assert ids
            qq.append(dict(q=q,text=ex.query,positive=ids))
        assert len(set(by[t].values()))==1
        put(RUN/'projection'/which/f'{t}.json.gz',dict(t=t,qs=qq,pool=[c.model_dump() for c in pool],digest=hashlib.sha256(raw).hexdigest()));n+=1
    print(i,n)
if __name__=='__main__':
    if sys.argv[1]=='assign':assignment()
    else:shard(int(sys.argv[1]))

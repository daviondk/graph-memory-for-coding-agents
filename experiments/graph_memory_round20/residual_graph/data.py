"""Recreate the native inputs by trajectory. Only supervised partitions have a label loader."""
from setup_graph import ROOT,RUN,TR,TRAINED,pilot,load,put,h
from collections import defaultdict
from functools import lru_cache
import json,sqlite3
from graph_memory.graphs.provenance import ProvenanceGraph
from graph_memory.retrieval.requests import ExecutionProvenanceRankingRequest,TextRankingRequest,TextCandidate
from graph_memory.evaluation.requests import EvidenceLabel
def split(which):return load(TR/'split.json.gz')[which]
@lru_cache
def graphfiles():
    plan=load(ROOT/'vectors-plan.json')
    out={}
    for i in range(8):
        p=RUN/f'graphs-{i}.json';assert pilot.sha(p)==plan['inputs'][p.name]
        for t,v in load(p).items():
            assert t not in out;out[t]=(RUN/'graphs'/f'{i}-{t}.json.gz',v)
    return out
def streams(stage):
    lookup=defaultdict(list)
    for r in split(stage):lookup[r['t']].append(r['q'])
    for t,ids in sorted(lookup.items()):
        p,w=graphfiles()[t];assert pilot.sha(p)==w
        rec=load(p);assert rec['t']==t and rec['split']==stage
        g=ProvenanceGraph.model_validate(rec['g']);pool=pilot.native.provenance_unit_candidates(g);qq=dict(rec['q'])
        assert set(qq)==set(ids);rs=[ExecutionProvenanceRankingRequest(task_id=q,query_text=qq[q],candidates=tuple(pool),graph=g) for q in ids]
        labels={}
        if stage in ('train','dev'):
            projected=load(TRAINED/'projection'/stage/f'{t}.json.gz')
            assert all(x.item_id==y['item_id'] and x.text==y['text'] for x,y in zip(pool,projected['pool'],strict=True))
            labels={v['q']:EvidenceLabel(task_id=v['q'],gold_answer='',gold_evidence_item_ids=tuple(v['positive']),gold_dependency_edges=()) for v in projected['qs']}
            assert set(labels)==set(ids)
        yield t,rs,labels
def ordered(values,stage):return [values[r['q']] for r in split(stage)]
def dev_rank():
    from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever
    from forecasts import Lookup
    from vectors import database
    c=database();ret=DenseTaskRetriever(encoder=Lookup(c,'ft'),device='cpu')
    allrows={};out={}
    for p in sorted((TRAINED/'projection/dev').glob('*.json.gz')):
        r=load(p);pool=tuple(TextCandidate.model_validate(x) for x in r['pool'])
        for q in r['qs']:
            rq=TextRankingRequest(task_id=q['q'],query_text=q['text'],candidates=pool)
            ranking=ret.rank(rq);assert {x.node_id for x in ranking}=={x.item_id for x in pool}
            packed=pilot.assemble_ranked_result(request=rq,method='dense',ranked_nodes=ranking,top_k=len(pool),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
            allrows[q['q']]=dict(q=q['q'],t=r['t'],rr=[x.model_dump() for x in packed])
    rows=ordered(allrows,'dev');put(ROOT/'dev500-pu-dense-ranks.json.gz',rows)
    put(ROOT/'dev500-pu-dense-lock.json',dict(ranks=pilot.sha(ROOT/'dev500-pu-dense-ranks.json.gz'),encoder=load(ROOT/'vectors-plan.json')['FT'],n=len(rows),candidates=sum(len(r['rr']) for r in rows)))
if __name__=='__main__':dev_rank()


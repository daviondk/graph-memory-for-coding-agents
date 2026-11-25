"""Source-only testing of exactly matched trained residual and its native seed signal."""
from collections import defaultdict
import sys,time,torch
from data import ROOT,RUN,TR,TRAINED,load,put,pilot,split
from setup_graph import CACHE
from fit_graph import model_cfg,build_model_from_config,materialize
from project import reqs
from graph_memory.models.graph_retriever.batching import build_evidence_dataloader,move_training_batch,split_batch_node_scores
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint
from graph_memory.retrieval.contracts import RankedNode
def lock():
    assert pilot.sha(RUN/'best.pt')==load(ROOT/'checkpoint.json')['sha']
    put(ROOT/'prediction-plan.json',dict(files={n:pilot.sha(ROOT/n) for n in ['PROTOCOL_RU.md','fit-lock.json','cost-ft.json','cost-base.json','pair-inventory.json','train-pairs.json.gz','checkpoint.json','infer_graph.py']},
        parents={n:pilot.sha(TR/n) for n in ['forecast-seal.json','split.json.gz']},prefix_skip_related=True))
def infer():
    from train import pin
    pin();L=load(ROOT/'prediction-plan.json');assert all(pilot.sha(ROOT/f)==v for f,v in L['files'].items())
    p=load_rgcn_checkpoint(RUN/'best.pt',map_location='cpu');assert p.model_config==model_cfg
    m=build_model_from_config(p.model_config);m.load_state_dict(p.payload['model_state_dict']);m=m.to('cuda').eval()
    zero=build_model_from_config(model_cfg).to('cuda').eval()
    st=time.monotonic();alltasks,_,_=materialize('test')
    graph=defaultdict(dict);seed=defaultdict(dict);lat=0
    for batch in build_evidence_dataloader(alltasks,per_device_graph_batch_size=128,shuffle=False,random_seed=13):
        b=move_training_batch(batch,'cuda');torch.cuda.synchronize();t=time.monotonic()
        with torch.inference_mode():score=m(b);null=zero(b)
        assert torch.equal(null,b.sample_node_features[:,0])
        torch.cuda.synchronize();lat+=time.monotonic()-t
        for target,values in ((graph,score),(seed,null)):
            for q,rows in split_batch_node_scores(batch,values).items():
                assert q not in target;target[q]=rows
    expected={r['q'] for r in split('test')};assert set(seed)==set(graph)==expected
    hashes={};joint=0;nodes=0;seen=set();standalone_all=standalone_first=0
    for i in range(8):
        reference={r['q']:r for r in load(TR/f'forecasts-main-{i}.json.gz')}
        result={'rgcn':[],'seed':[]}
        for p in sorted((CACHE/'projection').glob(f'{i}-*.json.gz')):
            row=load(p);requests=reqs(row)
            for req in requests:
                q=req.task_id;t=row['t'];ids={c.item_id for c in req.candidates};meta={c.item_id:c.metadata for c in req.candidates}
                assert q not in seen;seen.add(q)
                for name,value in (('rgcn',graph[q]),('seed',seed[q])):
                    assert {k for k,_ in value}==ids and len(value)==len(ids)
                    ranked=[RankedNode(node_id=k,score=v) for k,v in sorted(value,key=lambda x:(-x[1],x[0]))]
                    rr=pilot.assemble_ranked_result(request=req,method='provenance_rgcn',ranked_nodes=ranked,top_k=len(ids),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
                    arms={a:[n.node_id for n in pilot.pack(rr,meta,2048,a)] for a in ('prefix','skip','related')}
                    result[name].append(dict(q=q,t=t,rr=[n.model_dump() for n in rr],arms=arms))
                    if name=='seed':
                        compare=[x['node_id'] for x in reference[q]['rr']];assert set(compare)==ids
                        standalone_all+=compare==[n.node_id for n in rr];standalone_first+=compare[0]==rr[0].node_id
                joint+=set(k for k,_ in seed[q])==set(k for k,_ in graph[q]);nodes+=len(ids)
        for name,rr in result.items():
            f=f'forecasts-{name}-{i}.json.gz';put(ROOT/f,rr);hashes[f]=pilot.sha(ROOT/f)
    assert seen==expected
    put(ROOT/'forecast-seal.json',dict(plan=pilot.sha(ROOT/'prediction-plan.json'),forecasts=hashes,queries=len(seen),candidate_occurrences=nodes,matched_pools=joint,
        standalone_dense_complete_order_equal=standalone_all,standalone_dense_top1_equal=standalone_first,seconds_total=time.monotonic()-st,paired_gpu_forward_seconds=lat))
if __name__=='__main__':{'lock':lock,'infer':infer}[sys.argv[1]]()


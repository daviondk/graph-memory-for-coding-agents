"""Full-profile R-GCN calibrated dev ranks, produced from the selected checkpoint without labels."""
from pathlib import Path
import numpy as np,torch,time
from setup_graph import ROOT,RUN,TR,load,put,pilot
from data import streams,split
from vectors import database
from forecasts import Lookup
from fit_graph import model_cfg,features,tensorize_provenance_ranking_task,build_model_from_config
from graph_memory.models.graph_retriever.batching import collate_evidence_tasks,split_batch_node_scores
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint
from graph_memory.retrieval.contracts import RankedNode
def rank():
    torch.set_num_threads(8);ck=load(ROOT/'checkpoint.json');p=RUN/'best.pt';assert pilot.sha(p)==ck['sha']
    obj=load_rgcn_checkpoint(p,map_location='cpu');m=build_model_from_config(model_cfg);m.load_state_dict(obj.payload['model_state_dict']);m.eval()
    lookup=Lookup(database(),'ft');pending=[];rows=[];start=time.monotonic()
    def flush():
        b=collate_evidence_tasks([v for r,t,v in pending])
        with torch.inference_mode():scores=split_batch_node_scores(b,m(b))
        for r,t,v in pending:
            ranked=[RankedNode(node_id=k,score=z) for k,z in sorted(scores[r.task_id],key=lambda k:(-k[1],k[0]))]
            rr=pilot.assemble_ranked_result(request=r,method='provenance_rgcn',ranked_nodes=ranked,top_k=len(r.candidates),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
            meta={c.item_id:c.metadata for c in r.candidates}
            rows.append(dict(q=r.task_id,t=t,rr=[x.model_dump() for x in rr],arms={a:[x.node_id for x in pilot.pack(rr,meta,2048,a)] for a in ('prefix','skip','related')}))
        pending.clear()
    for t,rs,_ in streams('dev'):
        mat=np.empty((len(rs)*(len(rs[0].graph.nodes)+1),768),dtype='<f4');prov,end=features(rs,lookup,mat,0);assert end==len(mat)
        for r in rs:
            tensor=tensorize_provenance_ranking_task(r,model_config=model_cfg,text_embedding_provider=prov,seed_signal_provider=prov)
            pending.append((r,t,tensor))
            if len(pending)==64:flush()
    if pending:flush()
    assert len(rows)==500 and {r['q'] for r in rows}=={r['q'] for r in split('dev')}
    p=ROOT/'dev500-pu-rgcn-ranks.json.gz';put(p,rows);put(ROOT/'dev500-rgcn-lock.json',dict(ranks=pilot.sha(p),weights=ck['sha'],requests=len(rows),seconds=time.monotonic()-start))
if __name__=='__main__':rank()


"""Feasibility only: real native graph edges for 128 train requests; synthetic frozen features."""
import hashlib,sys,time
from collections import Counter
from types import SimpleNamespace
import torch
from prepare import ROOT,RUN,RAW,pilot,load,put
from train import pin
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
from graph_memory.models.graph_retriever.provenance import tensorize_provenance_edges
from graph_memory.models.graph_retriever.internals.neural import RGCNGraphEncoder,TypedRelationTransform
def edges():
    train=load(ROOT/'split.json.gz')['train']
    sample=sorted(train,key=lambda r:hashlib.sha256(('r19-rgcn-capacity|'+r['q']).encode()).digest())[:128]
    tids={r['t'] for r in sample};obs={}
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json')))
    for p in sorted(RAW.glob('trajectories-*.jsonl')):
        for _,obj in pilot.stream(p):
            t=obj['session_id']
            if t not in tids:continue
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=pilot.RAW[1]);g=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64))
            n=len(g.nodes)+1;ed=tensorize_provenance_edges(g);obs[t]=(n,ed)
    assert set(obs)==tids
    e=[];types=[];total=0
    for r in sample:
        n,d=obs[r['t']];e.append(d.edge_index+total);types.append(d.relation_ids);total+=n
    torch.save(dict(edges=torch.cat(e,1),types=torch.cat(types),nodes=total),RUN/'capacity.pt')
    put(ROOT/'rgcn-capacity-input.json',dict(queries=sample,nodes=total,edges=sum(x.numel() for x in types),physical_graphs=len(tids),types=[int(v) for v in torch.bincount(torch.cat(types),minlength=14)]))
def gpu():
    pin();d=torch.load(RUN/'capacity.pt',weights_only=True);t=torch.device('cuda');n=d['nodes'];e=d['edges'].to(t);rr=d['types'].to(t)
    E=RGCNGraphEncoder(hidden_dim=256,num_relations=14,num_layers=3,message_transform_factory=lambda:TypedRelationTransform(hidden_dim=256,num_relations=14),dropout=.1).to(t)
    proj=torch.nn.Linear(769,256).to(t);head=torch.nn.Linear(256,1).to(t);opt=torch.optim.AdamW([*E.parameters(),*proj.parameters(),*head.parameters()],lr=.0001)
    feat=torch.randn(n,769,device=t);batch=SimpleNamespace(edge_index=e,relation_ids=rr,edge_weights=torch.ones(len(rr),device=t))
    times=[]
    for i in range(4):
        opt.zero_grad(set_to_none=True);start=time.perf_counter();z=E(batch,proj(feat));y=head(z);loss=(y.square().mean());loss.backward();opt.step();torch.cuda.synchronize();times.append(time.perf_counter()-start)
    put(ROOT/'rgcn-capacity.json',dict(queries=128,nodes=n,message_edges=len(rr),seconds=times,peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,
        caveat='Native 3-layer graph encoder and real typed edges, FP32 optimizer/backprop; fixed random 769 features, dummy scalar head/loss. Capacity measurement only, not a trained or evaluated R-GCN.'))
if __name__=='__main__':{'edges':edges,'gpu':gpu}[sys.argv[1]]()

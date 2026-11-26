"""CPU reader timing with real release model weights and sealed per-query reference permutations."""
from pathlib import Path
from collections import defaultdict,Counter
from time import perf_counter_ns as tick
import os,sys,gzip,hashlib,json,platform,random,importlib.util,gc
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):os.environ[key]="1"
os.environ["CUDA_VISIBLE_DEVICES"]=""
import numpy as np,torch
from scipy.stats import rankdata
HERE=Path(__file__).resolve().parent;WORK=HERE.parents[1];R20=WORK/"graph_memory_round20"
OFF=WORK/"graph_memory_round22/native_multiseed/official580";TR=WORK/"graph_memory_round19/trained_rank";R33=WORK/"graph_memory_round33"
sys.path.insert(0,str(OFF));import official as of
from data import ProvenanceGraph,ExecutionProvenanceRankingRequest,graphfiles
from graph_memory.models.graph_retriever.batching import collate_evidence_tasks
from graph_memory.graphs.provenance import (ARGUMENT_CHUNK_NODE,OUTPUT_CHUNK_NODE,HAS_ARGUMENT_EDGE,HAS_CONTENT_EDGE,RETURNS_EDGE,NEXT_CHUNK_EDGE,FEEDS_EDGE,RESOURCE_FLOW_RELATION,logical_output_dependencies)
from graph_memory.models.graph_retriever.checkpoint import load_rgcn_checkpoint
ARMS=("dense","cost","full_rgcn","wo_chunk_adjacency")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,v):
    b=(json.dumps(v,sort_keys=True,separators=(",",":"))+"\n").encode();p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def pin():
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    from machine import pin_one
    return pin_one()
def params():
    model=get(R33/"relative_structure/weights.json")["models"]["global_role"];rank=get(R20/"factor_reader/hash64-weights.json")["rank"]
    p=get(R33/"budget_loss/selection.json")["policy"];corr=get(R33/"budget_loss/models.json")["models"][p]
    return {"structural":model,"rank":rank,"correction":{k:corr[k] for k in ("center","scale","weights","intercept")}}
def freeze():
    records=get(TR/"split.json.gz")["test"];ids=sorted(records,key=lambda r:hashlib.sha256(("R34 physical reader v1/"+r["q"]).encode()).digest())[:96]
    save(HERE/"linear-model.json",params())
    save(HERE/"plan.json",{"panel":[[r["q"],r["t"]] for r in ids],"protocol":sha(HERE/"PROTOCOL_RU.md"),"linear":sha(HERE/"linear-model.json"),"split":sha(TR/"split.json.gz")})
def net(m):
    pub,pr=of.seed_paths(13);r=get(pub/m/"fit.json");p=pr/r["attempt"]/"best.pt";assert sha(p)==r["checkpoint"]
    t=tick(); ck=load_rgcn_checkpoint(p,map_location="cpu"); neural=of.fit.build_model_from_config(ck.model_config).eval()
    neural.load_state_dict(ck.payload["model_state_dict"]);assert all(z.device.type=="cpu" for z in neural.parameters())
    elapsed=tick()-t
    return neural,ck.model_config,{"checkpoint_bytes":p.stat().st_size,"state_dict_payload":sum(v.numel()*v.element_size() for v in neural.state_dict().values()),"load_ns":elapsed,"sha":r["checkpoint"],"weight":r["weight"]}
def tree(file,t,qs):
    t0=tick();obj=get(file);assert obj["t"]==t and obj["split"]=="test";graph=ProvenanceGraph.model_validate(obj["g"])
    pool=tuple(of.pilot.native.provenance_unit_candidates(graph));texts=dict(obj["q"])
    reqs=[ExecutionProvenanceRankingRequest(task_id=q,query_text=texts[q],candidates=pool,graph=graph) for q in qs]
    return reqs,tick()-t0
def common_vectors(reqs,coder):
    b=np.empty(((len(reqs[0].graph.nodes)+1)*len(reqs),768),dtype="<f4");t=tick()
    prov,end=of.fit.features(reqs,coder,b,0);elapsed=tick()-t;assert end==len(b)
    return prov,elapsed,b.nbytes
def compile_struct(req,params):
    g=req.graph;items=sorted(req.candidates,key=lambda c:c.item_id);ids=[c.item_id for c in items];ix={k:i for i,k in enumerate(ids)};n=len(ids)
    returns={};args=defaultdict(list);outs=defaultdict(list);record=set()
    def link(a,b,k):
        if a!=b and a in ix and b in ix:record.add((ix[a],ix[b],k))
    for e in g.edges:
        if e.relation==HAS_ARGUMENT_EDGE:args[e.source].append(e.target)
        elif e.relation==HAS_CONTENT_EDGE:outs[e.source].append(e.target)
        elif e.relation==RETURNS_EDGE:returns[e.source]=e.target
        elif e.relation==NEXT_CHUNK_EDGE:link(e.source,e.target,0)
    for call,v in args.items():
        for a in v:
            for b in outs.get(returns.get(call),[]):link(a,b,1)
    for dep in logical_output_dependencies(g):
        typ=2 if dep.relation==FEEDS_EDGE else 3
        assert dep.relation in (FEEDS_EDGE,RESOURCE_FLOW_RELATION)
        for a in outs.get(dep.source_output_id,[]):
            for b in outs.get(dep.target_output_id,[]):link(a,b,typ)
    counts=np.zeros((n,8),dtype=int)
    for a,b,k in record:counts[a,2*k]+=1;counts[b,2*k+1]+=1
    freq=Counter(c.source_spans[0].event_id for c in items);x=[]
    for j,c in enumerate(items):
        m=c.metadata;e=freq[c.source_spans[0].event_id];pos=m["chunk_index"]
        x.append([int(m["node_kind"]=="content.tool_output"),np.log1p(m["token_count"]),np.log1p(pos),pos/max(1,e-1),int(pos==0),int(pos==e-1),np.log1p(e),*np.log1p(counts[j])])
    x=np.asarray(x);rel=np.empty((n,8))
    for role in (0,1):
        ii=np.flatnonzero(x[:,0]==role)
        if len(ii):rel[ii]=(rankdata(x[ii,7:],axis=0,method="average")-.5)/len(ii)-.5
    s=params["structural"];prior=np.column_stack((x,rel))@s["coef"]+s["intercept"]
    z=params["correction"];w=np.array(z["weights"])/z["scale"];base=np.column_stack((np.zeros(n),x[:,1],x[:,0],x[:,0]*x[:,1]))
    bias=prior+base@w-np.dot(z["center"],w)
    co=params["rank"];r=np.arange(1,n+1);rankval=np.column_stack((-np.log(r),1/r,(n-r)/max(1,n-1)))@co["coef"]+co["intercept"]+w[0]*np.log1p(r)
    return bias,rankval,len(record)
def fixed(req):
    cs=sorted(req.candidates,key=lambda c:c.item_id);ids=[c.item_id for c in cs];cost=np.array([c.metadata["token_count"] for c in cs])
    p={z.node_id:j for j,z in enumerate(req.graph.nodes)};ix=[p[k] for k in ids]
    return ids,cost,ix
def cos(mat,node_pos):
    query=mat[-1];return np.array([float(mat[i]@query) for i in node_pos],dtype=np.float32)
def batch(req,provider,cfg):
    task=of.fit.tensorize_provenance_ranking_task(req,model_config=cfg,text_embedding_provider=provider,seed_signal_provider=provider)
    return collate_evidence_tasks([task])
def finish(order,ids,cost):
    prefix=[];s=0
    for i in order:
        s+=cost[i]
        if s>2048:break
        prefix.append(ids[i])
    return [ids[i] for i in order],prefix
def simple(sem,ids,cost,static=None):
    p=np.argsort(-sem,kind="stable")
    if static is not None:
        bias,rankval,_=static;local=np.argsort(-(bias[p]+rankval),kind="stable");p=p[local]
    return finish(p,ids,cost)
def native(b,net1,ids,cost,perm):
    v=net1(b).detach().numpy()[perm];return finish(np.argsort(-v,kind="stable"),ids,cost)
def used_tensor_bytes(obj):
    # Real addressed storage in this materialized native dataclass, shared views counted once.
    import dataclasses
    def walk(x):
        if torch.is_tensor(x):
            store=x.untyped_storage();yield (str(x.device),store.data_ptr()),store.nbytes()
        elif dataclasses.is_dataclass(x):
            for f in dataclasses.fields(x):yield from walk(getattr(x,f.name))
        elif isinstance(x,dict):
            for v in x.values():yield from walk(v)
        elif isinstance(x,(tuple,list)):
            for v in x:yield from walk(v)
        elif hasattr(x,"model_fields"):
            for k in type(x).model_fields:yield from walk(getattr(x,k))
    return sum(dict(walk(obj)).values())
def references(panel):
    raw={};ranks={};c=get(R33/"budget_loss/test-ranks.json.gz");policy=get(R33/"budget_loss/selection.json")["policy"]
    for i in range(8):
        path=TR/f"forecasts-main-{i}.json.gz";base=get(path)
        refs={}
        for arm in ARMS[2:]:
            dir=OFF/"seed-13"/arm;rec=get(dir/"forecast-seal.json")["receipts"][i]
            assert sha(path)==rec["source"] and sha(dir/rec["file"])==rec["sha"];refs[arm]={r["q"]:r["graph"] for r in get(dir/rec["file"])}
        for r in base:
            q=r["q"]
            if q not in panel:continue
            rec=r["rr"];raw[q]={a["node_id"]:of.pilot.RankedNodeRecord.model_validate(a) for a in rec};ids=[x["node_id"] for x in rec]
            ranks[q]={"dense":ids,"cost":[ids[j] for j in c[q][policy]],**{m:[ids[j] for j in rr[q]] for m,rr in refs.items()}}
    assert set(raw)==panel
    return raw,ranks
if __name__=="__main__":freeze()

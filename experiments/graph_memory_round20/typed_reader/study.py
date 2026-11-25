"""Small CPU-only per-PU scoring over author-defined provenance neighbors. No raw text leaves source graphs."""
import os
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
    os.environ[k]="1"
import collections
import gzip
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path
import numpy as np
import sklearn
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
HERE=Path(__file__).resolve().parent
UP=Path(os.environ.get("GRAPHMEMORY_REPO","D:/CodexResearch/x20-isetrace-runtime/upstream"))
GRAPH=Path(os.environ.get("ISETRACE_RESIDUAL","D:/CodexResearch/x20-isetrace-residual"))
PROJ=Path(os.environ.get("ISETRACE_TRAINED","D:/CodexResearch/x20-isetrace-trained"))
RES=HERE.parent/"residual_graph"
TR=HERE.parent.parent/"graph_memory_round19/trained_rank"
OFF=HERE.parent.parent/"graph_memory_round18/isetrace_official"
sys.path.insert(0,str(UP))
from graph_memory.graphs.provenance import (ARGUMENT_CHUNK_NODE,OUTPUT_CHUNK_NODE,HAS_ARGUMENT_EDGE,HAS_CONTENT_EDGE,
    RETURNS_EDGE,NEXT_CHUNK_EDGE,FEEDS_EDGE,RESOURCE_FLOW_RELATION,ProvenanceGraph,logical_output_dependencies)
from graph_memory.models.graph_retriever.provenance import provenance_candidate_neighbor_edges
PROTO="aec63e5c6817ca6901e68898f6081e1d60431d267573fffa07321e81b5af0e6a"
MODELS=("rank_only","untyped","typed","shuffled")
ARMS=("dense",)+MODELS+("typed_on_shuffled",)
def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.name.endswith(".gz") else b)
def put(p,x):
    b=(json.dumps(x,separators=(",",":"),sort_keys=True,allow_nan=False)+"\n").encode()
    if p.name.endswith(".gz"):
        b=gzip.compress(b,compresslevel=5,mtime=0)
    if p.exists():
        assert b==p.read_bytes(),p
    else:
        p.write_bytes(b)
def graph_index():
    plan=read(RES/"vectors-plan.json")["inputs"]
    out={}
    for i in range(8):
        p=GRAPH/f"graphs-{i}.json"
        assert sha(p)==plan[p.name]
        for t,d in read(p).items():
            assert t not in out
            out[t]=(GRAPH/"graphs"/f"{i}-{t}.json.gz",d)
    return out

def project(t,index):
    p,h=index[t]
    assert sha(p)==h
    rec=read(p)
    assert t==rec["t"]
    g=ProvenanceGraph.model_validate(rec["g"])
    nodes=sorted((n.node_id,n.kind) for n in g.nodes if n.kind in (ARGUMENT_CHUNK_NODE,OUTPUT_CHUNK_NODE))
    ids={nid:i for i,(nid,_) in enumerate(nodes)}
    kinds=[k for _,k in nodes]
    args,outs=collections.defaultdict(list),collections.defaultdict(list)
    child={}
    triples=set()
    def link(a,b,kind):
        if a!=b and a in ids and b in ids:
            triples.add((ids[a],ids[b],kind))
    for edge in g.edges:
        a,b=edge.source,edge.target
        if edge.relation==HAS_ARGUMENT_EDGE:
            args[a].append(b)
        elif edge.relation==HAS_CONTENT_EDGE:
            outs[a].append(b)
        elif edge.relation==RETURNS_EDGE:
            child[a]=b
        elif edge.relation==NEXT_CHUNK_EDGE:
            link(a,b,0)
    for call,terms in args.items():
        for left in terms:
            for right in outs.get(child.get(call),[]):
                link(left,right,1)
    for d in logical_output_dependencies(g):
        assert d.relation in (FEEDS_EDGE,RESOURCE_FLOW_RELATION),d.relation
        k=2 if d.relation==FEEDS_EDGE else 3
        for left in outs.get(d.source_output_id,[]):
            for right in outs.get(d.target_output_id,[]):
                link(left,right,k)
    pairs={(min(a,b),max(a,b)) for a,b,z in triples}
    expected={(min(ids[e.source],ids[e.target]),max(ids[e.source],ids[e.target])) for e in provenance_candidate_neighbor_edges(g)}
    assert pairs==expected
    group=collections.defaultdict(list)
    for a,b,k in sorted(triples):
        group[k,kinds[a],kinds[b]].append((a,b))
    sham=set()
    swaps=0
    for key,values in sorted(group.items()):
        seed=int.from_bytes(hashlib.sha256((t+"|"+str(key)).encode()).digest()[:8],"big")
        rng=random.Random(seed)
        e=len(values)
        occupied=set(values)
        for _ in range(10*min(64,e) if e>=2 else 0):
            i,j=rng.sample(range(e),2)
            a,b=values[i]
            c,d=values[j]
            if a==c or b==d or a==d or c==b or (a,d) in occupied or (c,b) in occupied:
                continue
            occupied.remove((a,b));occupied.remove((c,d))
            occupied.update(((a,d),(c,b)));values[i]=(a,d);values[j]=(c,b)
            swaps+=1
        sham.update((a,b,key[0]) for a,b in values)
    def degrees(edges):
        return [collections.Counter((u[k],u[2]) for u in edges) for k in (0,1)]
    assert len(sham)==len(triples) and degrees(sham)==degrees(triples)
    def channels(edges):
        v=[[] for _ in range(8)]
        for a,b,k in sorted(edges):
            v[2*k].append((a,b))
            v[2*k+1].append((b,a))
        return [np.array(x,dtype=int).reshape(-1,2).T for x in v]
    undirected=np.array(sorted(pairs|{(b,a) for a,b in pairs}),dtype=int).reshape(-1,2).T
    return ids,channels(triples),channels(sham),[undirected],dict(t=t,nodes=len(ids),typed_arcs=len(triples),pairs=len(pairs),
       missing_query_independent_relations=[k for k in range(4) if not any(z==k for a,b,z in triples)],
       by_type=[sum(z==k for a,b,z in triples) for k in range(4)],changed=len(triples-sham),exchanges=swaps)

def project_rows(rr,gr):
    ids,real,fake,flat,_=gr
    order=np.array([ids[x["node_id"]] for x in rr],dtype=int)
    n=len(order)
    assert n==len(ids)==len(set(order.tolist()))
    rank=np.empty(n,dtype=float);rank[order]=np.arange(1,n+1)
    own=np.column_stack((-np.log(rank),1/rank,(n-rank)/max(1,n-1)))
    strength=1/np.log2(1+rank)
    def summary(ch):
        out=[]
        for dest,orig in ch:
            count=np.bincount(dest,minlength=n)
            total=np.bincount(dest,weights=strength[orig],minlength=n)
            best=np.zeros(n,dtype=float)
            np.maximum.at(best,dest,strength[orig])
            out.extend((np.log1p(count),best,np.log1p(total)))
        return np.column_stack([own]+out)[order]
    return dict(rank_only=own[order],untyped=summary(flat),typed=summary(real),shuffled=summary(fake))

def data_plan():
    dev=RES/"dev500-pu-dense-ranks.json.gz"
    assert sha(dev)==read(RES/"dev500-pu-dense-lock.json")["ranks"]
    hs=read(TR/"forecast-seal.json")["forecasts"]
    for f,v in hs.items():
        assert sha(TR/f)==v
    return dict(protocol=sha(HERE/"PROTOCOL_RU.md"),code=sha(Path(__file__)),dev=sha(dev),
        dev_split=sha(TR/"split.json.gz"),graph_plan=sha(RES/"vectors-plan.json"),test=hs,
        sklearn=sklearn.__version__,numpy=np.__version__,upstream="df29287116fa1565b3fd6b485022cd6090dc0b27")

def fit():
    assert sha(HERE/"PROTOCOL_RU.md")==PROTO
    plan=data_plan();put(HERE/"prediction-plan.json",plan)
    index=graph_index()
    rows=read(RES/"dev500-pu-dense-ranks.json.gz")
    by=collections.defaultdict(list)
    for r in rows:by[r["t"]].append(r)
    want=read(TR/"split.json.gz")
    assert {(r["q"],r["t"]) for r in rows}=={(r["q"],r["t"]) for r in want["dev"]}
    assert not set(by)&{r["t"] for r in want["test"]}
    X={a:[] for a in MODELS}
    ys=[];weights=[];aud=[];excluded=0
    for t,part in sorted(by.items()):
        gr=project(t,index);aud.append(gr[-1])
        labels={r["q"]:set(r["positive"]) for r in read(PROJ/"projection/dev"/(t+".json.gz"))["qs"]}
        for r in part:
            ids=[a["node_id"] for a in r["rr"]]
            positive=labels[r["q"]]
            assert positive<=set(ids)
            y=np.array([n in positive for n in ids],dtype=int)
            n1=int(y.sum());n0=len(y)-n1
            if not n1 or not n0:
                excluded+=1;continue
            x=project_rows(r["rr"],gr)
            for a in MODELS:X[a].append(x[a])
            ys.append(y);weights.append(np.where(y,.5/n1,.5/n0))
    y=np.concatenate(ys);w=np.concatenate(weights);w*=len(w)/w.sum()
    models={}
    for a in MODELS:
        x=np.concatenate(X[a])
        sc=StandardScaler().fit(x,sample_weight=w)
        z=LogisticRegression(C=1,solver="lbfgs",max_iter=1000,random_state=13)
        z.fit(sc.transform(x),y,sample_weight=w)
        assert max(z.n_iter_)<1000
        W=z.coef_[0]/sc.scale_
        b=float(z.intercept_[0]-np.dot(W,sc.mean_))
        assert np.allclose(x@W+b,z.decision_function(sc.transform(x)),rtol=1e-10,atol=1e-10)
        models[a]=dict(w=W.tolist(),bias=b,n_iter=int(z.n_iter_[0]),n_input=len(W))
    put(HERE/"weights.json",models);put(HERE/"dev-graph-audit.json.gz",aud)
    put(HERE/"fit-seal.json",dict(inputs=sha(HERE/"prediction-plan.json"),weights=sha(HERE/"weights.json"),
        audit=sha(HERE/"dev-graph-audit.json.gz"),queries=len(rows),excluded=excluded,used_queries=len(ys),nodes=len(y),positive=int(y.sum()),trajectories=len(aud)))
    print("FIT SEALED",len(rows),len(aud),len(y),int(y.sum()),excluded,flush=True)

def pack(order,cost,skip):
    chosen=[];used=0
    for i in order:
        j=int(i)
        if used+cost[j]>2048:
            if skip:continue
            break
        used+=cost[j];chosen.append(j)
    return chosen

def predict(part):
    s=read(HERE/"fit-seal.json")
    assert sha(HERE/"weights.json")==s["weights"] and sha(HERE/"prediction-plan.json")==s["inputs"]
    lock=read(HERE/"prediction-plan.json")
    assert lock["code"]==sha(Path(__file__)) and lock["protocol"]==sha(HERE/"PROTOCOL_RU.md")
    models=read(HERE/"weights.json")
    index=graph_index()
    fn=f"forecasts-main-{part}.json.gz";assert sha(TR/fn)==lock["test"][fn]
    by=collections.defaultdict(list)
    for r in read(TR/fn):by[r["t"]].append(r)
    audit=[];out=[];build_sec=score_sec=0.
    for t,group in sorted(by.items()):
        b=time.perf_counter()
        gr=project(t,index);audit.append(gr[-1])
        build_sec+=time.perf_counter()-b
        for r in group:
            tic=time.perf_counter()
            rr=r["rr"];cost=[n["token_count"] for n in rr];x=project_rows(rr,gr)
            sel={}
            for a in ARMS:
                if a=="dense":
                    o=np.arange(len(rr))
                else:
                    vec=x["shuffled" if a=="typed_on_shuffled" else a]
                    model=models["typed" if a=="typed_on_shuffled" else a]
                    o=np.argsort(-(vec@np.array(model["w"])+model["bias"]),kind="stable")
                sel[a]=dict(prefix=pack(o,cost,False),skip=pack(o,cost,True))
            for p in ("prefix","skip"):
                assert [rr[i]["node_id"] for i in sel["dense"][p]]==r["arms"][p]
            out.append(dict(q=r["q"],t=t,selection=sel))
            score_sec+=time.perf_counter()-tic
    pred=HERE/f"forecast-{part}.json.gz"
    put(pred,out);put(HERE/f"test-graphs-{part}.json.gz",audit)
    timer=HERE/f"time-{part}.json"
    if not timer.exists():put(timer,dict(graph_build_sec=build_sec,features_all_models_and_packing_sec=score_sec,queries=len(out),trajectories=len(audit)))
    print("PART",part,"queries",len(out),"graphs",len(audit),"seconds",round(build_sec+score_sec,2),flush=True)

def seal():
    expected={r["q"]:r["t"] for r in read(TR/"split.json.gz")["test"]}
    got={}
    hashes={}
    for i in range(8):
        p=HERE/f"forecast-{i}.json.gz";hashes[p.name]=sha(p)
        for r in read(p):
            assert r["q"] not in got and set(r["selection"])==set(ARMS)
            got[r["q"]]=r["t"]
    assert got==expected and len(got)==2000
    put(HERE/"forecast-seal.json",dict(fit=sha(HERE/"fit-seal.json"),forecasts=hashes,q=len(got),t=len(set(got.values()))))

if __name__=="__main__":
    cmd=sys.argv[1]
    if cmd=="fit":fit()
    elif cmd=="predict":
        for i in map(int,sys.argv[2:]):predict(i)
    elif cmd=="seal":seal()

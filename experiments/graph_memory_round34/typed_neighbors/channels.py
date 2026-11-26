"""Construct budget-matched semantic-neighbor features without reading evaluation labels."""
import os
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[key]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
import sys,json,gzip,hashlib,sqlite3
from pathlib import Path
from collections import defaultdict
D=Path(__file__).resolve().parent;WORK=D.parents[1]
B=WORK/"graph_memory_round33/budget_loss";sys.path.insert(0,str(B))
import data as old
from data import f,load,sha,np,nm,OLD,R19,R20,OFF,GRAPH,PROJ
CACHE=Path("D:/CodexResearch/x20-r34-typed-neighbors");CACHE.mkdir(exist_ok=True)
def save(p,o):
    b=json.dumps(o,sort_keys=True,separators=(",",":"),allow_nan=False).encode();tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix==".gz" else b);tmp.replace(p)
def prep(t,pool,idx):
    graph=f.gmod.project(t,idx);ids,shape=f.shape(pool,graph);where=graph[0]
    assert [where[k] for k in ids]==list(range(len(ids)))
    pm={v["item_id"]:v for v in pool};events={v["source_spans"][0]["event_id"] for v in pool}
    evindex={v:i for i,v in enumerate(sorted(events))};ev=np.array([evindex[pm[k]["source_spans"][0]["event_id"]] for k in ids]);role=shape[:,0].astype(int)
    ps=f.lin(old.MODEL,np.column_stack((shape,old.relative(shape,True))))
    def groups(chans):
        out=[];allpairs=[]
        for a,b in chans:
            cls=role[a]*2+role[b];parts=[]
            for g in np.unique(cls):
                aa=a[cls==g];bb=b[cls==g];n=len(role)
                assert len(set(zip(aa,bb)))==len(aa)
                parts.append((aa,bb,np.bincount(aa,minlength=n)))
            out.append(parts);allpairs.append(set(zip(a.tolist(),b.tolist())))
        return out,allpairs
    g,real=groups(graph[1]);sg,alt=groups(graph[2])
    for j in range(8):
        stats=lambda x:sorted((a,role[b]) for a,b in x)
        assert stats(real[j])==stats(alt[j])
    return where,ps,ev,g,sg,sum(len(real[j]-alt[j]) for j in range(0,8,2)),sum(len(real[j]) for j in range(0,8,2))
def inputs(order,geom):
    where,prior,ev,g,sg,changed,nedges=geom
    n=len(order);ind=np.asarray([where[k] for k in order]);assert len(ind)==n==len(set(ind.tolist()))==len(where)
    strength=np.empty(n);strength[ind]=1/np.log2(1+np.arange(1,n+1))
    def pool(ch):
        z=np.zeros((n,8));raw=np.zeros((n,8));best=np.full((n,8),-1,int)
        for k,parts in enumerate(ch):
            centered=np.zeros(n);var=np.zeros(n);rank=np.full(n,n,int)
            rank_order=np.empty(n,int);rank_order[ind]=np.arange(n)
            for a,b,c in parts:
                vals=strength[b];total=np.bincount(a,weights=vals,minlength=n);raw[:,k]+=total
                centered+=total-c*vals.mean()
                if len(vals)>1:var+=c*vals.var()*(len(vals)-c)/(len(vals)-1)
                np.minimum.at(rank,a,rank_order[b])
            present=rank<n
            best[present,k]=ev[ind[rank[present]]]
            np.divide(centered,np.sqrt(var),out=z[:,k],where=var>1e-15)
        z=np.clip(z,-3.,3.);ix=np.arange(n)
        l=z[:,:4].argmax(axis=1);r=4+z[:,4:].argmax(axis=1)
        new=np.maximum(0,np.minimum(z[ix,l],z[ix,r]))*(best[ix,l]!=best[ix,r])
        return np.log1p(raw[ind]),z[ind],new[ind]
    raw,z,agree=pool(g);_,sh,sa=pool(sg)
    return raw,z,agree,sh,sa,prior[ind]+f.lin(old.RANK,f.rank_x(n))
def prepare(stage):
    if stage=="test":assert load(D/"selection.json")["identified"]
    path=old.PRIVATE/(stage+".json.gz");assert sha(path)==load(B/(stage+"-input.json"))["features"]
    bases={v["q"]:v for v in load(path)}
    bf=load(B/"models.json")["models"]["cost_worst_0.03"];assert load(B/"selection.json")["policy"]=="cost_worst_0.03"
    ix=f.gmod.graph_index()
    def batches():
        if stage=="train":
            c=load(old.COHORT);ts=sorted({t for v in c.values() for t in v["t"]});con=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3").as_uri()+"?mode=ro",uri=True)
            reader=f.DenseTaskRetriever(encoder=f.Lookup(con,"ft"),device="cpu")
            for t in ts:
                p=load(PROJ/"train"/(t+".json.gz"));candidates=tuple(f.TextCandidate.model_validate(v) for v in p["pool"])
                rr=[]
                for q in p["qs"]:
                    order=[u.node_id for u in reader.rank(f.TextRankingRequest(task_id=q["q"],query_text=q["text"],candidates=candidates))]
                    rr.append((q["q"],order))
                yield t,p["pool"],rr
            con.close()
        else:
            if stage=="dev":
                for t,v in load(OFF/"dev-graphs.json").items():ix[t]=(GRAPH/(t+".json.gz"),v["graph_file"])
            for i,src in enumerate(old.sources(stage)):
                by=defaultdict(list)
                for r in load(src):by[r["t"]].append((r["q"],[p["node_id"] for p in r["rr"]]))
                for t,rr in by.items():
                    if stage=="dev":
                        g=f.gmod.ProvenanceGraph.model_validate(load(GRAPH/(t+".json.gz"))["g"])
                        pool=[v.model_dump(mode="json") for v in nm.pilot.native.provenance_unit_candidates(g)]
                    else:pool=load(f.app.rd.stream.CACHE/f"{i}-{t}.json.gz")["pool"]
                    yield t,pool,rr
    out=[];graphdiag={};count=defaultdict(int)
    for t,pool,rr in batches():
        geom=prep(t,pool,ix);graphdiag[t]=geom[-2:]
        for q,order in rr:
            b=bases.pop(q);raw,z,ag,sh,sa,base=inputs(order,geom);assert t==b["t"] and np.allclose(base,b["o"],rtol=0,atol=1e-12)
            off=base+((np.asarray(b["x"])-bf["center"])/bf["scale"])@bf["weights"]
            x=np.column_stack((1/np.log2(1+np.arange(1,len(base)+1)),raw,z,ag,sh,sa))
            assert np.all(np.isfinite(x))
            rec=dict(q=q,t=t,x=x.tolist(),o=off.tolist(),c=b["c"])
            if stage=="train":rec["y"]=b["y"]
            out.append(rec);count["rows"]+=len(ag);count["agree_rows"]+=int((ag>0).sum());count["agree_questions"]+=int(max(ag)>0)
            count["sham_rows_different"]+=int(np.any(np.abs(np.column_stack((z-sh,ag-sa)))>1e-10,axis=1).sum())
            count["sham_questions_different"]+=int(np.any(np.abs(z-sh)>1e-10) or np.any(np.abs(ag-sa)>1e-10))
    assert not bases
    pp=CACHE/(stage+".json.gz");save(pp,out)
    save(D/(stage+"-inputs.json"),{"n":len(out),"t":len(graphdiag),"identifier":count,"undirected_pairs_note":"Arc totals count each physical directed relation once.","arcs":sum(t[1] for t in graphdiag.values()),"changed_arcs":sum(t[0] for t in graphdiag.values()),"rows_file":sha(pp),"baseline_file":sha(path),"baseline_model":sha(B/"models.json"),"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"channels.py")})
    print(stage,len(out),dict(count),flush=True)
if __name__=="__main__":prepare(sys.argv[1])
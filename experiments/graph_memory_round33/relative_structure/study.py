"""Question-independent midranks of witnessed typed degrees for a frozen Dense-FT reader."""
import os
for name in ("MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[name]="1"
import sys
from pathlib import Path
from collections import defaultdict
from scipy.stats import rankdata
import numpy as np
ROOT=Path(__file__).resolve().parent;WORK=ROOT.parents[1]
R20=WORK/"graph_memory_round20";OLD=R20/"factor_reader";R19=WORK/"graph_memory_round19"
sys.path.insert(0,str(OLD))
import factor as f
import native_metrics as nm
import external as ext
from factor import load,save,sha
from concurrent.futures import ProcessPoolExecutor
MODES=("global","trajectory","role","global_trajectory","global_role")

def relative(x,by_role):
    out=np.empty((len(x),8),dtype=float)
    groups=[np.flatnonzero(x[:,0]==v) for v in (0,1)] if by_role else [np.arange(len(x))]
    for group in groups:
        if len(group):
            out[group]=(rankdata(x[group,7:],axis=0,method="average")-.5)/len(group)-.5
    return out

def design(x,mode,tr,role):
    if mode=="global":return x
    rel=role if mode.endswith("role") else tr
    return np.column_stack((x if mode.startswith("global") else x[:,:7],rel))

def fit():
    prior=load(OLD/"prior.json");split=load(R19/"trained_rank/split.json.gz")
    map_q={r["q"]:r["t"] for r in split["train"]}
    sizes={row["t"]:row["pu"] for i in range(8) for row in load(Path("D:/CodexResearch/x20-isetrace-trained/shape")/f"{i}.json.gz") if row["split"]=="train"}
    xx=[];zz=[];rr=[];ys=[];ws=[];parents={}
    for i,part in enumerate(prior["inventory"]):
        path=f.P/f"prior-{i}.npz";assert sha(path)==part["file"];parents[str(i)]=part["file"]
        a=np.load(path);x=a["x"];ys.append(a["y"]);ws.append(a["w"]);xx.append(x)
        start=0
        for q in part["q"]:
            n=sizes[map_q[q]];pool=x[start:start+n];start+=n
            assert len(pool)==n
            zz.append(relative(pool,False));rr.append(relative(pool,True))
        assert start==len(x)
    x=np.vstack(xx);tr=np.vstack(zz);role=np.vstack(rr);y=np.concatenate(ys);w=np.concatenate(ws)
    models={mode:f.lr(design(x,mode,tr,role),y,w) for mode in MODES}
    assert np.allclose(models["global"]["coef"],prior["models"]["prior"]["coef"],rtol=1e-7,atol=1e-7)
    save(ROOT/"weights.json",{"models":models,"q":prior["train_questions"],"trajectories":prior["train_trajectories"],"rows":len(y),
         "input_shards":parents,"rank_calibration":sha(OLD/"hash64-weights.json"),"protocol":sha(ROOT/"PROTOCOL_RU.md"),"code":sha(Path(__file__))})
    print("fit",len(y),flush=True)

def forecast(stage):
    dev=stage=="dev";i=None if dev else int(stage)
    src=R20/"untuned_holdout/dense-ranks-extra80.json.gz" if dev else f.app.rd.source("dense",i)
    baseline_file=OLD/("hash64-extra-ranks.json.gz" if dev else f"hash64-ranks-{i}.json.gz")
    rows=load(src);baseline={r["q"]:r for r in load(baseline_file)};by=defaultdict(list)
    for row in rows:by[row["t"]].append(row)
    index=load(ext.SPL)["records"] if dev else f.gmod.graph_index()
    model=load(ROOT/"weights.json")["models"];rank=load(OLD/"hash64-weights.json")["rank"];out=[]
    for t,qs in by.items():
        if dev:
            info=index[t];j=info["shard"];base=load(f.app.rd.DEV/f"{j}-{t}.json.gz")
            p=f.gmod.GRAPH/"graphs"/f"{j}-{t}.json.gz" if info["native"] else Path("D:/CodexResearch/x20-typed-reader-private")/(t+".json.gz")
            pool=[]
            for c in base["pool"]:
                m=c["metadata"];fn=ext._argument_chunk_node_id if m["node_kind"]=="content.tool_argument" else ext._output_chunk_node_id
                pool.append({**c,"item_id":fn(m["call_id"],m["chunk_index"])})
            graph=f.gmod.project(t,{t:(p,info["sha"])})
        else:
            pool=load(f.app.rd.stream.CACHE/f"{i}-{t}.json.gz")["pool"];graph=f.gmod.project(t,index)
        keys,x=f.shape(pool,graph);indices={k:j for j,k in enumerate(keys)};tr=relative(x,False);role=relative(x,True)
        pri={m:f.lin(model[m],design(x,m,tr,role)) for m in MODES}
        for row in qs:
            pos=[indices[c["node_id"]] for c in row["rr"]];signal=f.lin(rank,f.rank_x(len(pos)))
            orders={m:np.argsort(-(signal+p[pos]),kind="stable").tolist() for m,p in pri.items()}
            ref=baseline[row["q"]]["orders" if dev else "ranks"]["factor"]
            assert orders["global"]==ref,row["q"]
            out.append({"q":row["q"],"t":t,"orders":orders})
    name=f"ranks-{stage}.json.gz";save(ROOT/name,out)
    print("forecast",stage,len(out),flush=True);return name,sha(ROOT/name)

def evaluate(stage):
    dev=stage=="dev";i=None if dev else int(stage)
    src=R20/"untuned_holdout/dense-ranks-extra80.json.gz" if dev else f.app.rd.source("dense",i)
    refs=load(R19/"write_transfer/gold-spans.json.gz" if dev else nm.OFF/"gold-spans.json.gz")
    parents={r["q"]:r for r in load(src)}
    out={}
    for r in load(ROOT/f"ranks-{stage}.json.gz"):
        q=r["q"];rec=parents[q];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in rec["rr"]];gold=tuple(nm.pilot.SourceSpan.model_validate(s) for s in refs[q])
        out[q]={"t":r["t"],"arms":{}}
        for mode,order in {"dense":list(range(len(nodes))),**r["orders"]}.items():
            ranked=tuple(nodes[j] for j in order)
            vals=[nm.pilot.span_metrics_under_token_budget(ranked,gold,b) for b in (512,1024,2048)]
            out[q]["arms"][mode]=[vals[2].full_support,*[v.coverage for v in vals],nm.span_metrics_at(ranked,gold,5).coverage,nm.span_mrr(ranked,gold)]
    save(ROOT/f"outcomes-{stage}.json.gz",out)
    print("scored",stage,len(out),flush=True);return out

def aggregate(rows):
    return {m:np.mean([r["arms"][m] for r in rows.values()],axis=0).tolist() for m in ["dense",*MODES]}
def paired(rows,m):
    groups=defaultdict(list)
    for q,r in sorted(rows.items()):groups[r["t"]].append(np.array(r["arms"][m])-r["arms"]["global"])
    units=[groups[t] for t in sorted(groups)];n=len(units)
    sizes=np.array(list(map(len,units)));sums=np.asarray([np.sum(g,axis=0) for g in units]);rng=np.random.default_rng(33);boot=[]
    for _ in range(100):
        samples=rng.integers(n,size=(100,n));boot.extend(sums[samples].sum(axis=1)/sizes[samples].sum(axis=1)[:,None])
    return {"delta_pp":(100*sums.sum(axis=0)/sizes.sum()).tolist(),"ci95_pp":(100*np.quantile(boot,[.025,.975],axis=0)).tolist(),
            "fs_wins":sum(r["arms"][m][0]>r["arms"]["global"][0] for r in rows.values()),"fs_losses":sum(r["arms"][m][0]<r["arms"]["global"][0] for r in rows.values())}

def main():
    fit();forecast("dev");dev=evaluate("dev");av=aggregate(dev)
    chosen=max(MODES,key=lambda k:(av[k][0],av[k][3],-MODES.index(k)))
    save(ROOT/"dev-selection.json",{"chosen":chosen,"dev":av,"weights":sha(ROOT/"weights.json"),"ranks":sha(ROOT/"ranks-dev.json.gz"),"program":sha(Path(__file__))})
    print("dev selection",chosen,flush=True)
    with ProcessPoolExecutor(2) as pool:ranks=dict(pool.map(forecast,map(str,range(8))))
    save(ROOT/"test-seal.json",{"ranks":ranks,"selection":sha(ROOT/"dev-selection.json"),"study":sha(Path(__file__))})
    rows={}
    with ProcessPoolExecutor(2) as pool:
        for part in pool.map(evaluate,map(str,range(8))):assert rows.keys().isdisjoint(part);rows.update(part)
    assert len(rows)==2000
    historical=load(OLD/"metrics-test-rows.json.gz")
    for q,r in rows.items():
        for arm,old in (("dense","dense"),("global","factor")):
            check=historical[old][q];assert np.allclose(r["arms"][arm],[check[n] for n in ("full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr")],atol=1e-12)
    result={"metrics":["FS2048","C512","C1024","C2048","R5","MRR"],"questions":len(rows),"trajectories":len({r["t"] for r in rows.values()}),
            "means":aggregate(rows),"chosen":chosen,"vs_global":{m:paired(rows,m) for m in MODES if m!="global"},"seal":sha(ROOT/"test-seal.json")}
    save(ROOT/"results.json",result);print("complete",result["chosen"],flush=True)
if __name__=="__main__":main()

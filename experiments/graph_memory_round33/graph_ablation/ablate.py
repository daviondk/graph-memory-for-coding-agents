"""Matched factorial graph/no-edge ablation of a token-cost ranking loss."""
import sys,sqlite3
from collections import Counter,defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"budget_loss"))
import losses as b
from study import paired
import numpy as np
load,save,sha=b.load,b.save,b.sha
PRIVATE=Path("D:/CodexResearch/x20-r33-graph-ablation")
PRIOR=load(b.OLD/"prior.json")["models"]["shape"]
MODES=("rank","metadata","graph")
KEYS=("FS2048","C512","C1024","C2048","R5","MRR")
def from_rr(rows):
    events=Counter(r["source_spans"][0]["event_id"] for r in rows)
    out=[]
    for r in rows:
        name=r["node_id"]; k=int(name.rsplit(":chunk:",1)[1]);n=events[r["source_spans"][0]["event_id"]]
        assert name.startswith(("argument:","output-content:")) and 0<=k<n
        out.append([int(name.startswith("output-content:")),np.log1p(r["token_count"]),np.log1p(k),k/max(1,n-1),int(k==0),int(k==n-1),np.log1p(n)])
    return np.asarray(out)
def metadata(stage):
    if stage!="train":
        for i,p in enumerate(b.sources(stage)):
            check={r["q"]:r["ranks"]["shape"] for r in load(b.OLD/f"hash64-ranks-{i}.json.gz")} if stage=="test" else {}
            for r in load(p):
                x=from_rr(r["rr"]);score=b.f.lin(PRIOR,x)
                if check:
                    signal=b.f.lin(b.RANK,b.f.rank_x(len(x)))
                    assert np.argsort(-(signal+score),kind="stable").tolist()==check[r["q"]]
                yield r["q"],score,x
        return
    cohort=load(b.COHORT); trajectories=sorted({t for z in cohort.values() for t in z["t"]})
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3").as_uri()+"?mode=ro",uri=True)
    reader=b.f.DenseTaskRetriever(encoder=b.f.Lookup(db,"ft"),device="cpu")
    for t in trajectories:
        r=load(b.PROJ/"train"/(t+".json.gz"));pool=r["pool"]
        candidates=tuple(b.f.TextCandidate.model_validate(v) for v in pool)
        node={z["item_id"]:{"node_id":z["item_id"],"source_spans":z["source_spans"],"token_count":z["metadata"]["token_count"]} for z in pool}
        for q in r["qs"]:
            ids=[v.node_id for v in reader.rank(b.f.TextRankingRequest(task_id=q["q"],query_text=q["text"],candidates=candidates))]
            x=from_rr([node[i] for i in ids]);yield q["q"],b.f.lin(PRIOR,x),x
    db.close()
def prep(stage):
    upstream=b.PRIVATE/(stage+".json.gz");assert sha(upstream)==load(b.ROOT/(stage+"-input.json"))["features"]
    original={r["q"]:r for r in load(upstream)};new={}
    for q,score,x in metadata(stage):
        src=original[q];oldx=np.asarray(src["x"]);assert np.allclose(x[:,0],oldx[:,2]) and np.allclose(x[:,1],oldx[:,1])
        new[q]=score.tolist()
    assert len(new)==len(original)
    save(PRIVATE/(stage+".json.gz"),new)
    save(HERE/(stage+"-inputs.json"),{"count":len(new),"offsets":sha(PRIVATE/(stage+".json.gz")),"upstream":sha(upstream),"metadata_weights":sha(b.OLD/"prior.json"),"protocol":sha(HERE/"PROTOCOL_RU.md"),"code":sha(Path(__file__))})
def data(stage):
    info=load(HERE/(stage+"-inputs.json"));p=PRIVATE/(stage+".json.gz");assert sha(p)==info["offsets"] and sha(b.PRIVATE/p.name)==info["upstream"]
    shape=load(p)
    for rec in load(b.PRIVATE/p.name):
        n=len(rec["c"]);sig=b.f.lin(b.RANK,b.f.rank_x(n))
        yield rec,{"rank":sig,"metadata":sig+shape[rec["q"]],"graph":np.asarray(rec["o"])}
def fit():
    parents=load(b.ROOT/"models.json")["models"];models={}
    for a in MODES:
        train=b.arrays([{**r,"o":o[a].tolist()} for r,o in data("train")])
        for kind in ("point","cost_worst"):
            for l2 in b.K:
                name=f"{kind}_{l2}";m=b.solve(train,kind,l2)
                if a=="graph":assert np.allclose(m["weights"],parents[name]["weights"],rtol=0,atol=1e-9)
                models[a+"."+name]=m
    save(HERE/"models.json",models)
def forecast(stage):
    models=load(HERE/"models.json");sel=load(HERE/"select.json") if stage=="test" else list(models);rows={}
    for r,offset in data(stage):
        x=np.asarray(r["x"]);rr={}
        for a in MODES:rr[a+".frozen"]=np.argsort(-offset[a],kind="stable").tolist()
        for name in sel:
            m=models[name];a=name.split(".",1)[0]
            score=offset[a]+(x-m["center"])/m["scale"]@m["weights"]
            rr[name]=np.argsort(-score,kind="stable").tolist()
        rows[r["q"]]=rr
    p=HERE/(stage+"-ranks.json.gz");save(p,rows)
    save(HERE/(stage+"-seal.json"),{"ranks":sha(p),"models":sha(HERE/"models.json"),"inputs":sha(HERE/(stage+"-inputs.json")),"selection":sha(HERE/"select.json") if stage=="test" else None})
def evaluate(stage):
    p=HERE/(stage+"-ranks.json.gz");assert sha(p)==load(HERE/(stage+"-seal.json"))["ranks"]
    ranks=load(p);old=load(b.ROOT/(stage+"-ranks.json.gz"));refs=load(b.R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else b.nm.OFF/"gold-spans.json.gz")
    out={}
    for src in b.sources(stage):
        for r in load(src):
            q=r["q"];nodes=[b.nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];gold=tuple(b.nm.pilot.SourceSpan.model_validate(v) for v in refs[q])
            rec={}
            for name,order in ranks[q].items():
                if name.startswith("graph."):assert old[q][name.split(".",1)[1]]==order
                ns=tuple(nodes[i] for i in order);cs=[b.nm.pilot.span_metrics_under_token_budget(ns,gold,k) for k in (512,1024,2048)]
                rec[name]=[cs[-1].full_support,*[v.coverage for v in cs],b.nm.span_metrics_at(ns,gold,5).coverage,b.nm.span_mrr(ns,gold)]
            out[q]={"t":r["t"],"arms":rec}
    save(HERE/(stage+"-outcomes.json.gz"),out);means={k:np.mean([r["arms"][k] for r in out.values()],axis=0).tolist() for k in next(iter(out.values()))["arms"]}
    save(HERE/(stage+"-means.json"),means)
    if stage=="dev":
        selected=[]
        for a in MODES:
            for kind in ("point","cost_worst"):
                candidates=[f"{a}.{kind}_{l}" for l in sorted(b.K,reverse=True)]
                selected.append(max(candidates,key=lambda n:(round(means[n][0],12),round(means[n][3],12),-candidates.index(n))))
        save(HERE/"select.json",selected);return
    sel=dict(((n.split(".")[0],n.split(".",1)[1].rsplit("_",1)[0]),n) for n in load(HERE/"select.json"))
    a=sel["graph","cost_worst"];c=sel["metadata","cost_worst"];d=sel["rank","cost_worst"]
    arms={"graph_minus_metadata":{a:1,c:-1},"graph_minus_rank":{a:1,d:-1},"difference_in_differences":{a:1,"graph.frozen":-1,c:-1,"metadata.frozen":1},"metadata_gain":{c:1,"metadata.frozen":-1},"graph_gain":{a:1,"graph.frozen":-1}}
    stats={}
    for name,coeff in arms.items():
        rows={q:{"t":r["t"],"arms":{"global":[0.]*len(KEYS),"candidate":sum(v*np.asarray(r["arms"][k]) for k,v in coeff.items()).tolist()}} for q,r in out.items()}
        stats[name]=paired(rows,"candidate")
    save(HERE/"results.json",{"metrics":KEYS,"n":len(out),"clusters":len({r["t"] for r in out.values()}),"means":means,"contrasts":stats})
if __name__=="__main__":
    for stage in ("train","dev","test"):
        prep(stage)
        if stage=="train":fit()
        else:forecast(stage);evaluate(stage)
        print(stage,flush=True)

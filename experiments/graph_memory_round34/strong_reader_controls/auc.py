"""Evaluate the frozen orders with all six official budgets and the native log-budget AUC."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from collections import defaultdict
import gzip, hashlib, json,sys
HERE=Path(__file__).resolve().parent; WORK=HERE.parents[1]
R33=WORK/"graph_memory_round33";sys.path.insert(0,str(R33/"budget_loss"))
from data import nm, np, sources
from graph_memory.evaluation.span_suite import normalized_budget_auc, CONTEXT_TOKEN_BUDGETS
from bounds import read,save,sha,NATIVE,DATA,SEEDS
NATIVE_HOME=WORK/"graph_memory_round22/native_multiseed/official580/seed-13"
SOURCES=("frozen","cost","fixed_count")
GRAPH=("full_rgcn","wo_chunk_adjacency")
B=CONTEXT_TOKEN_BUDGETS
assert tuple(B)==(256,512,1024,2048,4096,8192)

def shard(i):
    source=sources("test")[i]; original=read(source);rankfile=DATA/f"repeat-ranks-{i}.json.gz"
    ranks=read(rankfile); old=read(DATA/f"repeat-outcomes-{i}.json.gz")
    metrics13=read(NATIVE); gold=read(nm.OFF/"gold-spans.json.gz"); arcs={};checks={"candidate":sha(rankfile),"pool":sha(source)}
    for m in GRAPH:
        h=NATIVE_HOME/m; r=read(h/"forecast-seal.json")["receipts"][i]
        p=h/r["file"]; assert sha(p)==r["sha"] and sha(source)==r["source"]
        checks[m]=r["sha"];arcs[m]={t["q"]:t for t in read(p)}
    out={}
    for record in original:
        q=record["q"];assert record["t"]==metrics13[q][0]; nodes=[nm.pilot.RankedNodeRecord.model_validate(n) for n in record["rr"]]
        ref=tuple(nm.pilot.SourceSpan.model_validate(v) for v in gold[q]);cache={}; out[q]={"t":record["t"],"seeds":{}}
        for seed in SEEDS:
            orders={m:ranks[q][seed][m] for m in SOURCES}
            if seed=="13":orders.update({m:arcs[m][q]["graph"] for m in GRAPH})
            vals={}
            for m,order in orders.items():
                key=tuple(order)
                if key not in cache:
                    assert sorted(key)==list(range(len(nodes)))
                    ns=tuple(nodes[j] for j in key); v=[nm.pilot.span_metrics_under_token_budget(ns,ref,b) for b in B]
                    c=[x.coverage for x in v]; f=[float(x.full_support) for x in v]
                    cache[key]=[normalized_budget_auc(dict(zip(B,c))),normalized_budget_auc(dict(zip(B,f))),*c,*f]
                a=cache[key];vals[m]=a
                former=old[q]["seeds"][seed][m][6] if m in SOURCES else metrics13[q][2+GRAPH.index(m)][0]
                assert a[11]==former
                if m in SOURCES:assert np.allclose(a[2:7],old[q]["seeds"][seed][m][1:6],atol=1e-12,rtol=0)
            out[q]["seeds"][seed]=vals
    p=HERE/f"auc-outcomes-{i}.json.gz";save(p,out);return p.name,sha(p),checks

def summarize(rows,seeds,models):
    qs=sorted(rows)
    av=np.array([[[rows[q]["seeds"][s][m] for s in seeds] for m in models] for q in qs]).mean(axis=2)
    means=dict(zip(models,(100*av.mean(axis=0)).tolist()))
    pairs=[("cost","frozen"),("fixed_count","cost")]+([("cost",g) for g in GRAPH] if len(seeds)==1 else [])
    delta=np.stack([av[:,models.index(a),:2]-av[:,models.index(b),:2] for a,b in pairs],axis=1)
    terms=defaultdict(list)
    for j,q in enumerate(qs):terms[rows[q]["t"]].append(j)
    ordered=sorted(terms);groups=[terms[t] for t in ordered];n=len(groups)
    sizes=np.array(list(map(len,groups)));sums=np.array([delta[idx].sum(0).ravel() for idx in groups])
    rng=np.random.default_rng(13);samples=[]
    for _ in range(100):
        ids=rng.integers(n,size=(100,n))+n*np.arange(100)[:,None]
        w=np.bincount(ids.ravel(),minlength=100*n).reshape(100,n);samples.append(w@sums/(w@sizes)[:,None])
    bounds=(100*np.quantile(np.concatenate(samples),[.025,.975],axis=0)).reshape(2,len(pairs),2)
    return {"means_pct":means,"differences":{a+" minus "+b:{"delta_pp":(100*delta.mean(axis=0)[k]).tolist(),"ci95_pp":bounds[:,k,:].tolist()} for k,(a,b) in enumerate(pairs)}}
def main():
    with ProcessPoolExecutor(2) as ex:parts=list(ex.map(shard,range(8)))
    rows={}
    for name,h,_ in parts: assert sha(HERE/name)==h;rows.update(read(HERE/name))
    assert len(rows)==2000 and len({v["t"] for v in rows.values()})==1207
    save(HERE/"auc.json",{"panels":{"all5":summarize(rows,SEEDS,SOURCES),"seed13":summarize(rows,SEEDS[:1],(*SOURCES,*GRAPH))},
        "metrics":["Coverage Budget-AUC","Full Support Budget-AUC",*["C"+str(b) for b in B],*["FS"+str(b) for b in B]],"parts":parts,
        "protocol":sha(HERE/"AUC_PROTOCOL_RU.md"),"script":sha(Path(__file__)),"upstream_auc":sha(Path(sys.modules[normalized_budget_auc.__module__].__file__))})
if __name__=="__main__":main()

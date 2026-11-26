"""Read sealed orders, evaluate using upstream native span metrics and paired trajectory sampling."""
from input_rows import D,PRIVATE,W,R19,R20,OFF,devparents,testparents,load,sha,write,pilot,np
from models import FAMILIES,K,ALPHAS
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget,span_metrics_at,span_mrr
from collections import defaultdict
KEYS=("full_support","coverage","recall5","mrr")
def score(split):
    preds=D/(split+"-ranks.json.gz");seal=load(D/(split+"-seal.json"));assert sha(preds)==seal["rank"]
    if split=="test":assert seal["selection"]==sha(D/"dev-selection.json")
    armids=seal["arms"];cells={k:{} for k in armids}
    truth=load(R19/"write_transfer/gold-spans.json.gz" if split=="dev" else W/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    groups={r["q"]:r for r in load(preds)}
    for src in devparents() if split=="dev" else testparents():
        for base in load(src):
            q=base["q"];r=groups.pop(q);assert r["t"]==base["t"]
            rr=[pilot.RankedNodeRecord.model_validate(x) for x in base["rr"]]
            gold=tuple(pilot.SourceSpan.model_validate(x) for x in truth[q])
            for a,perm in r["rank"].items():
                assert sorted(perm)==list(range(len(rr)));ordered=tuple(rr[j] for j in perm)
                m=span_metrics_under_token_budget(ordered,gold,2048)
                vals=[m.full_support,m.coverage]
                if split=="test":vals.extend([span_metrics_at(ordered,gold,5).coverage,span_mrr(ordered,gold)])
                cells[a][q]=[r["t"],*vals]
    assert not groups
    outcome=D/(split+"-outcomes.json.gz");write(outcome,cells)
    ns=len(cells["factor"]);keys=KEYS[:2] if split=="dev" else KEYS
    summary={a:{k:float(np.mean([v[i+1] for v in rs.values()])) for i,k in enumerate(keys)} for a,rs in cells.items()}
    tab=D/(split+"-metrics.json")
    write(tab,{"n":ns,"t":len({v[0] for v in cells["factor"].values()}),"summary":summary,"outcomes":sha(outcome),"preds":sha(preds),"upstream_metric":sha(W.parents[1]/"x20-isetrace-runtime/upstream/graph_memory/evaluation/span_metrics.py") if (W.parents[1]/"x20-isetrace-runtime/upstream/graph_memory/evaluation/span_metrics.py").exists() else None,"evaluator":sha(D/"score.py")})
    if split=="dev":
        def best(names):return max(names,key=lambda a:(summary[a]["full_support"],summary[a]["coverage"]))
        a=best([f"alpha_{v}" for v in ALPHAS]);g=best([f"global_{v}" for v in K]);t=best([f"{s}_{k}" for s in FAMILIES[1:] for k in K])
        b=best(["factor",a,g])
        write(D/"dev-selection.json",{"models":sha(D/"models.json"),"metrics":sha(tab),"seal":sha(D/"dev-seal.json"),"selected":{"constant":a,"nonlinear":g,"control":b,"conditional":t},"test":False})
    else:
        hist=load(W/"graph_memory_round21/five_seed/seed-13/metrics.json.gz")
        for a in ("dense","factor"):
            for q,(t,*v) in cells[a].items():
                x=hist[a][q];assert x["t"]==t and max(abs(i-x[k]) for i,k in zip(v,("full_support_2048","coverage_2048","recall_5","mrr"),strict=True))<1e-12
        sel=load(D/"dev-selection.json")["selected"];pairs={}
        for a,b in dict.fromkeys([(sel["conditional"],sel["control"]),(sel["conditional"],"factor"),(sel["control"],"factor"),("factor","dense")]):
            groups=defaultdict(list)
            for q in sorted(cells[a]):
                t,*v=cells[a][q];tr,*u=cells[b][q];assert t==tr;groups[t].append(np.asarray(v)-u)
            dd=np.asarray([np.sum(groups[t],axis=0) for t in sorted(groups)]);counts=np.asarray([len(groups[t]) for t in sorted(groups)])
            vals=np.concatenate(list(groups.values()));rng=np.random.default_rng(13);bs=[]
            for _ in range(40):
                ix=rng.integers(len(counts),size=(250,len(counts)));bs.append(dd[ix].sum(axis=1)/counts[ix].sum(axis=1)[:,None])
            cis=np.quantile(np.concatenate(bs),[.025,.975],axis=0)
            pairs[f"{a}-vs-{b}"]={k:{"delta":float(vals[:,j].mean()),"ci":cis[:,j].tolist(),"wins":int(sum(vals[:,j]>1e-12)),"losses":int(sum(vals[:,j]<-1e-12))} for j,k in enumerate(KEYS)}
        write(D/"paired.json",{"pairs":pairs,"historical_baseline_exact":True,"metrics":sha(tab),"trajectory_draws":10000,"seed":13})
if __name__=="__main__":
    import sys
    score(sys.argv[1])
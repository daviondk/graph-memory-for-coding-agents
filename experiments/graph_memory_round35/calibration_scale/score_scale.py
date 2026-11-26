"""Paired evaluation against the official source-span and budget-AUC implementations."""
from prepare_scale import *
from graph_memory.evaluation.span_suite import normalized_budget_auc,CONTEXT_TOKEN_BUDGETS
from collections import defaultdict
BS=tuple(sorted(CONTEXT_TOKEN_BUDGETS))
METRICS=["FullSupport2048","CoverageBudgetAUC","FullSupportBudgetAUC","MRR","Coverage2048"]
def native(nodes,gold,order):
    seq=tuple(nodes[i] for i in order);p=b.nm.pilot
    vals=[p.span_metrics_under_token_budget(seq,gold,k) for k in BS];c=[v.coverage for v in vals];s=[v.full_support for v in vals]
    return [s[BS.index(2048)],normalized_budget_auc(dict(zip(BS,c))),normalized_budget_auc(dict(zip(BS,s))),b.nm.span_mrr(seq,gold),c[BS.index(2048)]]
def measure(stage):
    p=D/(stage+"-orders.json.gz");seal=load(D/(stage+"-seal.json"));assert seal["orders"]==sha(p) and seal["fit"]==sha(D/"models.json") and seal["selection"]==sha(D/"selection.json");orders=load(p)
    ref=b.R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else b.nm.OFF/"gold-spans.json.gz"
    refs=load(ref);old=load(B/(stage+"-outcomes.json.gz"));out={};checks=0
    for i,src in enumerate(b.sources(stage)):
        if stage=="test":ha=load(W/f"graph_memory_round34/strong_reader_controls/auc-outcomes-{i}.json.gz")
        for rec in load(src):
            q=rec["q"];nodes=tuple(b.nm.pilot.RankedNodeRecord.model_validate(s) for s in rec["rr"]);gold=tuple(b.nm.pilot.SourceSpan.model_validate(s) for s in refs[q])
            memo={};arms={}
            for m,o in orders[q].items():
                k=tuple(o);assert len(set(k))==len(nodes) and sorted(k)==list(range(len(nodes)))
                if k not in memo:memo[k]=native(nodes,gold,k);checks+=1
                arms[m]=memo[k]
            h=old[q]["arms"]["cost_worst_0.03"];a=arms["original_R33"];assert np.allclose([a[0],a[3],a[4]],[h[0],h[5],h[3]])
            if stage=="test":assert np.allclose(ha[q]["seeds"]["13"]["cost"][:2],a[1:3],atol=1e-12)
            out[q]=dict(t=rec["t"],arms=arms)
    assert len(out)==(580 if stage=="dev" else 2000)
    p=D/(stage+"-outcomes.json.gz");save(p,out);mean={a:np.mean([v["arms"][a] for v in out.values()],axis=0).tolist() for a in next(iter(out.values()))["arms"]}
    allresults=dict(metrics=METRICS,means=mean,n=len(out),trajectories=len({v["t"] for v in out.values()}),budgets=BS,unique_order_query_pairs=checks,seal=sha(D/(stage+"-seal.json")),outcomes=sha(p))
    if stage=="test":
        counter=[*(("oof_3894",other) for other in ("original_R33","oof_196","oof_1024","full_3894","rotated_3894")),
            *(("oof_1024",other) for other in ("oof_196","full_1024","rotated_1024")),
            *(("oof_196",other) for other in ("full_196","rotated_196","original_R33"))]
        q=sorted(out);ts=sorted({out[k]["t"] for k in q});tc={t:i for i,t in enumerate(ts)};ids=np.array([tc[out[k]["t"]] for k in q]);cnt=np.bincount(ids);diffs=[]
        for a,bx in counter:diffs.append(np.asarray([out[k]["arms"][a] for k in q])-np.asarray([out[k]["arms"][bx] for k in q]))
        diff=np.asarray(diffs).transpose(1,0,2);summed=np.zeros((len(ts),len(counter),len(METRICS)));np.add.at(summed,ids,diff)
        rng=np.random.default_rng(35035);boot=[]
        for _ in range(100):
            samp=rng.integers(len(ts),size=(100,len(ts)))
            # Compress the repeated trajectory positions into multiplicities per bootstrap row.
            counts=np.stack([np.bincount(row,minlength=len(ts)) for row in samp]);boot.append((counts@summed.reshape(len(ts),-1)).reshape(100,len(counter),len(METRICS))/(counts@cnt)[:,None,None])
        iv=100*np.quantile(np.concatenate(boot),[.025,.975],axis=0);contrasts={}
        for j,(aa,bb) in enumerate(counter):contrasts[aa+" minus "+bb]=dict(delta_pp=(100*diff[:,j].mean(0)).tolist(),ci95_pp=iv[:,j].tolist(),
            win=(diff[:,j]>1e-12).sum(0).tolist(),loss=(diff[:,j]<-1e-12).sum(0).tolist(),
            changed_orders=sum(orders[k][aa]!=orders[k][bb] for k in q))
        allresults.update(contrasts=contrasts)
    save(D/(stage+"-results.json"),allresults);print(stage,[(k,round(v[0]*100,2)) for k,v in mean.items()],flush=True)
if __name__=="__main__":measure(sys.argv[1])
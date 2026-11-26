"""Use native span coverage and separately audit the proxy based on positive nodes."""
from losses import *
from collections import Counter
from study import paired
KEYS=["FS2048","C512","C1024","C2048","R5","MRR"]
def best(names,means):
    # Near-identical means in the two grid points are resolved by their stated complexity.
    return max(names,key=lambda m:(round(means[m][0],12),round(means[m][3],12),-names.index(m)))
def main(stage):
    p=ROOT/(stage+"-ranks.json.gz");seal=load(ROOT/(stage+"-seal.json"));assert sha(p)==seal["rank"]
    if stage=="test":assert seal["selection"]==sha(ROOT/"selection.json")
    ranks=load(p);refs=load(R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else nm.OFF/"gold-spans.json.gz");out={};inputs=sources(stage);label_cache={};diagnostic={}
    for path in inputs:
        for r in load(path):
            q=r["q"];t=r["t"];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];gold=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q]);arms={}
            if stage=="dev":
                if t not in label_cache:label_cache[t]=load(GRAPH/(t+".json.gz"))["labels"]
                positive=set(label_cache[t][q])
            for m,order in ranks[q].items():
                assert sorted(order)==list(range(len(nodes)))
                ranked=tuple(nodes[j] for j in order)
                vals=[nm.pilot.span_metrics_under_token_budget(ranked,gold,k) for k in (512,1024,2048)]
                arms[m]=[vals[2].full_support,*[v.coverage for v in vals],nm.span_metrics_at(ranked,gold,5).coverage,nm.span_mrr(ranked,gold)]
                if stage=="dev":
                    ids=[n.node_id for n in ranked];idx=max(i for i,n in enumerate(ids) if n in positive)
                    assert positive<=set(ids)
                    pos_cost=sum(n.token_count for n in ranked if n.node_id in positive)
                    neg_cost=sum(n.token_count for n in ranked[:idx] if n.node_id not in positive)
                    proxy=int(pos_cost+neg_cost<=2048);key=f"proxy{proxy}_native{int(vals[2].full_support)}"
                    diagnostic.setdefault(m,Counter())[key]+=1
            out[q]={"t":t,"arms":arms}
    assert out.keys()==ranks.keys()
    save(ROOT/(stage+"-outcomes.json.gz"),out)
    names=list(next(iter(out.values()))["arms"]);means={m:np.mean([r["arms"][m] for r in out.values()],axis=0).tolist() for m in names}
    summary={"n":len(out),"metrics":KEYS,"means":means,"outcomes":sha(ROOT/(stage+"-outcomes.json.gz")),"seal":sha(ROOT/(stage+"-seal.json"))}
    if stage=="dev":
        chosen={k:best([f"{k}_{l}" for l in sorted(K,reverse=True)],means) for k in FAM};policy=best(["frozen",*chosen.values()],means)
        save(ROOT/"selection.json",{"chosen":chosen,"policy":policy,"models":sha(ROOT/"models.json"),"evaluation":sha(ROOT/"evaluate.py"),"dev":summary["outcomes"]})
        summary["surrogate"]=diagnostic
    else:
        chosen=load(ROOT/"selection.json")["chosen"];summary["vs"]={}
        reference={}
        for i in range(8):reference.update(load(REL/f"outcomes-{i}.json.gz"))
        for q,r in out.items():assert np.allclose(reference[q]["arms"]["global_role"],r["arms"]["frozen"],rtol=0,atol=1e-12)
        for m,b in [(v,"frozen") for v in chosen.values()]+[(chosen["cost_worst"],chosen[k]) for k in FAM if k!="cost_worst"]:
            cells={q:{"t":r["t"],"arms":{"global":r["arms"][b],"candidate":r["arms"][m]}} for q,r in out.items()}
            summary["vs"][m+" vs "+b]=paired(cells,"candidate")
    save(ROOT/(stage+"-results.json"),summary)
    print(stage,{k:round(v[0],5) for k,v in means.items()},flush=True)
if __name__=="__main__":main(sys.argv[1])

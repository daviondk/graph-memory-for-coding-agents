from geometry import *
from study import paired
KEYS=["full_support_2048","coverage_512","coverage_1024","coverage_2048","coverage_top5","mrr"]
def row_metrics(atoms,order,c):
    ix=np.asarray(order,dtype=int);assert sorted(ix.tolist())==list(range(len(c)))
    rank=np.argsort(ix);cum=np.cumsum(c[ix]);assert (c>0).all()
    assert all(ids for *_,ids in atoms)
    first=np.asarray([min(rank[i] for i in ids) for *_,ids in atoms]);length=np.asarray([b-a for _,a,b,_ in atoms]);last=int(max(first))
    cost=int(cum[last]);hit=lambda b:float(length[cum[first]<=b].sum()/length.sum())
    score=[int(cost<=2048),hit(512),hit(1024),hit(2048),float(length[first<5].sum()/length.sum()),float(1/(first.min()+1))]
    pos={i for *_,g in atoms for i in g};lastp=max(rank[i] for i in pos);neg_cost=sum(int(c[i]) for i in ix[:last+1] if i not in pos)
    surplus=pos-{g[0] for g in buckets(atoms) if len(g)==1};optional_cost=sum(int(c[i]) for i in ix[:last+1] if i in surplus)
    return score,dict(atomic_rank=last+1,all_positive_rank=int(lastp+1),atomic_prefix_tokens=cost,all_positive_prefix_tokens=int(cum[lastp]),true_distractor_tokens=neg_cost,nonessential_positive_tokens=optional_cost)
def native(nodes,g,order):
    seq=tuple(nodes[i] for i in order);p=old.nm.pilot
    v=[p.span_metrics_under_token_budget(seq,g,k) for k in (512,1024,2048)]
    return [v[-1].full_support,*[r.coverage for r in v],old.nm.span_metrics_at(seq,g,5).coverage,old.nm.span_mrr(seq,g)]
def avg(rows):
    return {k:np.mean([r["arms"][k] for r in rows.values()],axis=0).tolist() for k in next(iter(rows.values()))["arms"]}
def pick(opts,means):return max(opts,key=lambda n:(round(means[n][0],12),round(means[n][3],12),-opts.index(n)))
def evaluate(stage):
    p=D/(stage+"-ranks.json.gz");seal=load(D/(stage+"-rank-seal.json"));assert sha(p)==seal["ranks"]
    rks=load(p);atoms=load(D/(stage+"-atoms.json.gz"))
    ref=old.R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else old.nm.OFF/"gold-spans.json.gz";refs=load(ref);out={};detail={}
    hist=load(B/(stage+"-outcomes.json.gz"));audit=Counter();seen=set()
    for path in old.sources(stage):
        for ex in load(path):
            q=ex["q"];rr=ex["rr"];c=np.asarray([r["token_count"] for r in rr]);nd=tuple(old.nm.pilot.RankedNodeRecord.model_validate(v) for v in rr)
            g=tuple(old.nm.pilot.SourceSpan.model_validate(v) for v in refs[q]);arms={};diag={};memo={}
            for n,ix in rks[q].items():
                order=tuple(ix)
                if order not in memo:
                    a,s=row_metrics(atoms[q],order,c);official=native(nd,g,order);assert np.allclose(a,official,rtol=0,atol=1e-12),(q,n,a,official)
                    audit["unique_query_orders_checked"]+=1;memo[order]=a,s
                a,s=memo[order];arms[n]=a;diag[n]=s;audit["query_methods_checked"]+=1
                if n=="cost_worst_0.03":assert np.allclose(hist[q]["arms"][n],a,rtol=0,atol=1e-12)
            assert q not in seen;seen.add(q);out[q]=dict(t=ex["t"],arms=arms);detail[q]=diag
    assert len(out)==(580 if stage=="dev" else 2000)
    vals=avg(out);p=D/(stage+"-outcomes.json.gz");save(p,out);save(D/(stage+"-costs.json.gz"),detail)
    summary=dict(n=len(seen),t=len({r["t"] for r in out.values()}),metrics=KEYS,means=vals,native_checks=dict(audit),
        outcomes=sha(p),costs=sha(D/(stage+"-costs.json.gz")),ranks=seal["ranks"],atoms=sha(D/(stage+"-atoms.json.gz")))
    if stage=="dev":
        fam=["cost_worst","cost_log","per_positive","fixed","witness"];chosen={f:pick([f+"_"+str(r) for r in (.3,.03)],vals) for f in fam}
        chosen["control"]=pick([chosen[f] for f in fam[:-1]],vals);save(D/"dev-results.json",summary)
        save(D/"selection.json",dict(chosen=chosen,means=vals,primary="witness minus dev-best control",selection=sha(D/"dev-results.json"),fit=sha(D/"models.json"),evaluator=sha(Path(__file__))))
        print("dev",chosen,flush=True);return
    chosen=load(D/"selection.json")["chosen"];w=chosen["witness"];result={}
    for baseline in dict.fromkeys(chosen.values()):
        temp={q:dict(t=r["t"],arms={"global":r["arms"][baseline],"new":r["arms"][w]}) for q,r in out.items()}
        z=paired(temp,"new");z["distinct_orders"]=sum(rks[q][w]!=rks[q][baseline] for q in out)
        for subset,flag in (("any_alternative_atom",lambda a:any(len(g)>1 for *_,g in a)),("minimal_alternative_group",lambda a:any(len(g)>1 for g in buckets(a)))):
            cond=[q for q in out if flag(atoms[q])];z[subset]=dict(n=len(cond),win=sum(out[q]["arms"][w][0]>out[q]["arms"][baseline][0] for q in cond),loss=sum(out[q]["arms"][w][0]<out[q]["arms"][baseline][0] for q in cond))
        result[baseline]=z
    ss={}
    for name in vals:
        a=[v[name] for v in detail.values()]
        ss[name]={"earlier_rank":sum(x["atomic_rank"]<x["all_positive_rank"] for x in a),"native_full_missing_in_positive_proxy":sum(x["atomic_prefix_tokens"]<=2048<x["all_positive_prefix_tokens"] for x in a),"total_nonessential_tokens_in_complete_prefix":sum(x["nonessential_positive_tokens"] for x in a)}
    save(D/"results.json",dict(**summary,chosen=chosen,paired_vs=result,prefix=ss,classification="exploratory_reused_benchmark"))
    print("test", {n:round(z[0]*100,3) for n,z in vals.items()},ss[chosen["cost_worst"]],flush=True)
if __name__=="__main__":evaluate(sys.argv[1])
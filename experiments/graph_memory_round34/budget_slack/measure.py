"""Native span measurements after all seed-specific ranks are frozen."""
from slack import D,B,W,old,nm,R19,np,load,sha,save,SEEDS,TRANS,K
from collections import defaultdict
import sys
KEYS=("FS2048","C2048","R5","MRR")
def score(rr,gold,perm):
    nodes=tuple(rr[i] for i in perm);v=nm.pilot.span_metrics_under_token_budget(nodes,gold,2048)
    return [v.full_support,v.coverage,nm.span_metrics_at(nodes,gold,5).coverage,nm.span_mrr(nodes,gold)]
def means(rows):
    first=next(iter(rows.values()))
    return {a:np.mean([r["arms"][a] for r in rows.values()],axis=0).tolist() for a in first["arms"]}
def pick(order,values):return max(order,key=lambda a:(round(values[a][0],12),round(values[a][1],12),-order.index(a)))
def dev():
    p=D/"dev-ranks.json.gz";seal=load(D/"dev-seal.json");assert seal["ranks"]==sha(p)
    ranks=load(p);refs=load(R19/"write_transfer/gold-spans.json.gz");out={};history=load(B/"dev-ranks.json.gz")
    for src in old.sources("dev"):
        for ex in load(src):
            q=ex["q"];r=ranks[q];assert r["r33_flat_0.03"]==history[q]["cost_worst_0.03"]
            rr=[nm.pilot.RankedNodeRecord.model_validate(v) for v in ex["rr"]];g=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q]);out[q]={"t":ex["t"],"arms":{a:score(rr,g,ix) for a,ix in r.items()}}
    assert len(out)==580;pp=D/"dev-outcomes.json.gz";save(pp,out);v=means(out)
    family=lambda n:[f"{n}_{s}_{k}" for s in TRANS for k in K]
    c={"baseline":"r33_flat_0.03","equal":pick([f"equal_flat_{k}" for k in K],v),"length":pick(family("length"),v),"slack":pick(family("slack"),v)}
    c["control"]=pick([c["baseline"],c["equal"],c["length"]],v);c["matched_length"]=c["slack"].replace("slack_","length_")
    save(D/"dev-results.json",dict(n=len(out),means=v,keys=KEYS,outcomes=sha(pp)));save(D/"selection.json",dict(chosen=c,dev=sha(D/"dev-results.json"),models=sha(D/"models.json"),protocol=sha(D/"PROTOCOL_RU.md"),primary="slack-control mean across all five matched seeds",evaluator=sha(D/"measure.py")))
    print(c,{k:round(v[n][0]*100,2) for k,n in c.items()})
def summarize(rows,seeds,names,c):
    by={a:[] for a in names};ts=[]
    for q in sorted(rows):
        cell=rows[q];ts.append(cell["t"])
        for a in names:by[a].append(np.mean([cell["seeds"][str(seed)][a] for seed in seeds],axis=0))
    by={a:np.array(z) for a,z in by.items()};groups=defaultdict(list)
    for j,t in enumerate(ts):groups[t].append(j)
    bundle=[groups[t] for t in sorted(groups)];ns=np.array([len(ix) for ix in bundle]);out={}
    for b in dict.fromkeys([c["control"],c["baseline"],c["length"],c["matched_length"],c["equal"]]):
        diff=by[c["slack"]]-by[b];sums=np.array([diff[ix].sum(axis=0) for ix in bundle]);rng=np.random.default_rng(13);blocks=[]
        for _ in range(40):
            ix=rng.integers(len(ns),size=(250,len(ns)));blocks.append(sums[ix].sum(axis=1)/ns[ix].sum(axis=1)[:,None])
        ci=np.quantile(np.concatenate(blocks),[.025,.975],axis=0)
        out[b]={k:dict(delta=float(diff[:,j].mean()),lo=float(ci[0,j]),hi=float(ci[1,j]),win_questions=int((diff[:,j]>1e-12).sum()),loss_questions=int((diff[:,j]<-1e-12).sum())) for j,k in enumerate(KEYS)}
    return {"means":{a:z.mean(axis=0).tolist() for a,z in by.items()},"vs":out}
def test():
    seal=load(D/"test-seal.json");assert seal["chosen"]==sha(D/"selection.json") and seal["models"]==sha(D/"models.json")
    c=load(D/"selection.json")["chosen"];names=list(dict.fromkeys(c.values()))
    refs=load(nm.OFF/"gold-spans.json.gz");out={};history13=load(B/"test-outcomes.json.gz")
    for i,src in enumerate(old.sources("test")):
        p=D/f"test-ranks-{i}.json.gz";assert sha(p)==seal["files"][p.name]
        ranks=load(p);hist=load(B/f"transfer-outcomes-{i}.json.gz")
        for ex in load(src):
            q=ex["q"];rr=tuple(nm.pilot.RankedNodeRecord.model_validate(v) for v in ex["rr"]);g=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q]);cur={}
            for seed in SEEDS:
                ss=str(seed);ro=ranks[q][ss];memo={};vals={}
                for a in names:
                    ix=tuple(ro[a]);assert sorted(ix)==list(range(len(rr)))
                    if ix not in memo:memo[ix]=score(rr,g,ix)
                    vals[a]=memo[ix]
                historical=history13[q]["arms"] if seed==13 else hist[q]["seeds"][ss]
                val=historical["cost_worst_0.03"];assert vals[c["baseline"]]==[val[j] for j in (0,3,4,5)]
                cur[ss]=vals
            out[q]={"t":ex["t"],"seeds":cur}
        print("scored",i,len(out),flush=True)
    assert len(out)==2000 and len({r["t"] for r in out.values()})==1207
    pp=D/"test-outcomes.json.gz";save(pp,out);groups=[("all5",SEEDS),("transfer4",SEEDS[1:])]+[(str(s),[s]) for s in SEEDS]
    results={k:summarize(out,seeds,names,c) for k,seeds in groups}
    save(D/"results.json",dict(n=len(out),t=1207,keys=KEYS,data=results,chosen=c,seal=sha(D/"test-seal.json"),outcomes=sha(pp)))
if __name__=="__main__":{"dev":dev,"test":test}[sys.argv[1]]()
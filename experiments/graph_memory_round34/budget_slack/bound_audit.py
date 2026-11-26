"""Verify the prefix lemma, tie handling and native/PU discrepancy without retraining."""
from slack import D,B,old,nm,R19,np,load,sha,save,SEEDS
from collections import Counter
from itertools import permutations,product
from scipy.special import logsumexp
import sys
def check_small():
    histories=0;violations=0;uncorrected=0
    for n in (2,3,4):
        c=np.arange(1,n+1)
        for bits in product((0,1),repeat=n):
            y=np.asarray(bits,bool)
            if y.all() or not y.any():continue
            for ix in permutations(range(n)):
                a=np.array(ix);positive=y[a];P=int(c[y].sum());N=int(c[~y].sum());last=np.flatnonzero(positive)[-1]
                A=int(c[a[:last]][~positive[:last]].sum())
                for budget in range(1,int(c.sum())+1):
                    L=budget-P+1;prefix=a[np.cumsum(c[a])<=budget]
                    miss=int(not set(np.flatnonzero(y))<=set(prefix))
                    assert miss==int(P+A>budget)
                    if L>0:assert miss<=A/L+1e-12
                    else:assert miss==1
                    histories+=1
        # Include tied scores and scores near the minimum, which expose normalized softmin's limitation.
        for sv in product((0.,.1,.3,2.),repeat=n):
            scores=np.array(sv);order=np.argsort(-scores,kind="stable")
            for bits in product((0,1),repeat=n):
                y=np.array(bits,bool)
                if not y.any() or y.all():continue
                low=-.25*logsumexp(-scores[y]/.25);normalized=low+.25*np.log(y.sum())
                costs=c[~y]/c[~y].sum();ordered=y[order];last=np.flatnonzero(ordered)[-1]
                A=c[order[:last]][~ordered[:last]].sum()/c[~y].sum()
                hard=costs@(np.logaddexp(0,scores[~y]-scores[y].min())/np.log(2));corrected=costs@(np.logaddexp(0,scores[~y]-low)/np.log(2))
                norm=costs@(np.logaddexp(0,scores[~y]-normalized)/np.log(2))
                assert A<=hard+1e-12 and A<=corrected+1e-12
                uncorrected+=int(A>norm+1e-12)
    return {"prefix_lemma_order_budget_cases":histories,"uncorrected_softmin_surrogate_counterexamples":uncorrected}
def flagged(nodes,truth):
    by={}
    for g in truth:by.setdefault((g["event_id"],g["json_pointer"]),[]).append((g["char_start"],g["char_end"]))
    return np.array([any(max(a,s["char_start"])<min(b,s["char_end"]) for s in v["source_spans"] for a,b in by.get((s["event_id"],s["json_pointer"]),[])) for v in nodes],bool)
def audit(stage):
    if stage=="test":assert (D/"results.json").exists()
    refs=load(R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else nm.OFF/"gold-spans.json.gz");chosen=load(D/"selection.json")["chosen"]
    names=list(dict.fromkeys(chosen.values()));outcomes=load(D/(stage+"-outcomes.json.gz"));audit=Counter();roll={};rows={}
    for i,src in enumerate(old.sources(stage)):
        ranks=load(D/("dev-ranks.json.gz" if stage=="dev" else f"test-ranks-{i}.json.gz"))
        for ex in load(src):
            q=ex["q"];rr=ex["rr"];c=np.array([v["token_count"] for v in rr],int);y=flagged(rr,refs[q]);P=int(c[y].sum());N=int(c[~y].sum());L=2048-P+1;assert y.any()
            audit["questions"]+=1;audit["impossible"]+=int(L<=0);audit["guaranteed"]+=int(P+N<=2048)
            pos=tuple(nm.pilot.RankedNodeRecord.model_validate(v) for j,v in enumerate(rr) if y[j])
            g=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q]);covered=nm.pilot.span_metrics_under_token_budget(pos,g,max(1,P)).full_support==1
            audit["positive_union_covers_gold"]+=int(covered);row=dict(t=ex["t"],P=P,N=N,positive_count=int(y.sum()),order={})
            for seed in ([13] if stage=="dev" else SEEDS):
                ss=str(seed);rank=ranks[q] if stage=="dev" else ranks[q][ss];stats=outcomes[q]["arms"] if stage=="dev" else outcomes[q]["seeds"][ss]
                row["order"][ss]={}
                for arm in names:
                    ix=np.array(rank[arm]);ordpos=y[ix];last=np.flatnonzero(ordpos)[-1];A=int(c[ix[:last]][~ordpos[:last]].sum());proxy=int(P+A<=2048)
                    budget=c[ix].cumsum();assert proxy==int(np.all(budget[ordpos]<=2048))
                    native=int(stats[arm][0]);z=roll.setdefault(ss+"|"+arm,Counter())
                    if L>0:assert 1-proxy<=A/L+1e-14
                    if covered:assert proxy<=native
                    z[f"proxy{proxy}_native{native}"]+=1;row["order"][ss][arm]=[A,proxy,native]
            rows[q]=row
    pp=D/(stage+"-proxy.json.gz");save(pp,rows)
    save(D/(stage+"-bound.json"),dict(conditions=dict(audit),confusion=roll,proof_checks=check_small(),rows=sha(pp),code=sha(D/"bound_audit.py")))
if __name__=="__main__":audit(sys.argv[1])
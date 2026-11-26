"""Use the official budgeted scorer and independently check every packet against source-span atoms."""
import argparse
import sys
from packet import D,W,read,save,sha,np,THRESHOLDS,B

def measure(stage,seed):
    pref=f"{stage}-{seed}";pred=D/(pref+"-pred.json.gz");receipt=read(D/(pref+"-seal.json"))
    assert receipt["packet"]==sha(pred)
    if stage=="test":
        assert all((D/f"test-{s}-seal.json").is_file() for s in (13,17,29,37,41))
    rows=read(pred);sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"));import data as upstream
    axis=read(W/f"graph_memory_round34/interval_witness/{stage}-atoms.json.gz")
    ref=(upstream.R19/"write_transfer" if stage=="dev" else upstream.nm.OFF)/"gold-spans.json.gz";refs=read(ref)
    out={};checks=0;packets=0
    for src in upstream.sources(stage):
        for row in read(src):
            q=row["q"];t,arms=rows[q];assert t==row["t"]
            nodes=tuple(upstream.nm.pilot.RankedNodeRecord.model_validate(n) for n in row["rr"])
            g=tuple(upstream.nm.pilot.SourceSpan.model_validate(n) for n in refs[q]);memo={};scores={}
            spans=[(hi-lo,set(ids)) for _,lo,hi,ids in axis[q]];length=sum(n for n,_ in spans)
            for name,ids in arms.items():
                s=frozenset(ids);assert len(s)==len(ids)
                if s not in memo:
                    seq=tuple(nodes[i] for i in ids);cost=sum(n.token_count for n in seq);assert cost<=B
                    v=upstream.nm.pilot.span_metrics_under_token_budget(seq,g,B)
                    total=sum(n for n,ix in spans if not ix.isdisjoint(s))
                    assert abs(total/length-v.coverage)<1e-12 and int(total==length)==v.full_support
                    memo[s]=[int(v.full_support),v.coverage,cost,len(seq)]
                scores[name]=memo[s];packets+=1
            out[q]=[t,scores];checks+=len(memo)
    assert out.keys()==rows.keys()
    means={k:np.mean([i[1][k] for i in out.values()],axis=0).tolist() for k in next(iter(out.values()))[1]}
    save(D/(pref+"-outcomes.json.gz"),out)
    save(D/(pref+"-scores.json"),dict(means=means,checks=checks,packets=packets,rows=len(rows),predictions=sha(pred),
        official_gold=sha(ref),outcomes=sha(D/(pref+"-outcomes.json.gz")),code=sha(D/"score.py")))
    if stage=="dev":
        thresholds={name:max(THRESHOLDS,key=lambda t:(*means[f"{name}-{t}-dp"][:2],t)) for name in ("graph","dense")}
        save(D/"dev-selection.json",dict(thresholds=thresholds,dev=sha(D/(pref+"-scores.json")),frozen_models=sha(D/"models.json")))
        print("dev",thresholds,flush=True)
    print(pref,{n:round(v[0]*100,2) for n,v in means.items()},flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage");p.add_argument("seeds",nargs="+",type=int);a=p.parse_args()
    for s in a.seeds:measure(a.stage,s)


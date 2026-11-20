"""Evaluate sealed decisions against subsequently read accepted spans."""
from collections import Counter
import numpy as np
from run import D, E, e, read, save, gzip, rows
def main():
    for n,h in read("decision_lock.json").items():assert e.sha((D/n).read_bytes())==h
    for n,h in read("method_lock.json").items():
        from pathlib import Path
        assert e.sha(Path(n).read_bytes())==h
    names=["recent","pointwise","global","history","typed","placebo"]
    evaluated=[];allcuts=0; seen=set(); counts=Counter()
    for k in range(8):
        pred={(i,t):(a,cost) for i,t,a,cost in rows(D/f"pred_{k}.jsonl.gz")};allcuts+=len(pred)
        seen.update(i for i,t in pred)
        for i,t,span,oracle in rows(D/f"gold_{k}.jsonl.gz"):
            choices,cost=pred[i,t]
            hits={a:int(bool(span) and set(span)<=set(choices[a])) for a in names}
            for a in names:assert len(choices[a])==len(set(choices[a]))<=3 and hits[a]<=oracle
            evaluated.append([i,t,span,oracle,hits,cost])
    with gzip.open(D/"scored.jsonl.gz","wt",encoding="utf8") as out:
        for x in evaluated:e.packed(out,x)
    proj=sorted({r[0].split(".")[0] for r in evaluated});N=len(evaluated)
    effect={}
    for a in names:
        delta=np.array([r[4]["typed"]-r[4][a] for r in evaluated])
        reps=[[int(delta[[j for j,r in enumerate(evaluated) if r[0].split(".")[0]==p]].sum()),sum(r[0].split(".")[0]==p for r in evaluated)] for p in proj]
        sums,num=np.array(reps).T;rng=np.random.default_rng(261118)
        b=rng.integers(len(proj),size=(10000,len(proj)))
        effect[a]=dict(wins=int((delta==1).sum()),losses=int((delta==-1).sum()),delta=float(delta.mean()),ci=np.quantile(sums[b].sum(axis=1)/num[b].sum(axis=1),[.025,.975]).tolist(),repo_macro=float((sums/num).mean()),by_project=dict(zip(proj,reps)))
    save("results.json",{"n":N,"all_cuts":allcuts,"seen_instances":len(seen),"included_instances":len({r[0] for r in evaluated}),"projects":len(proj),"upper_bound":sum(r[3] for r in evaluated),"hits":{a:sum(x[4][a] for x in evaluated) for a in names},
         "mean_characters":{a:sum(x[5][a] for x in evaluated)/N for a in names},"typed_minus":effect,"gold_width":dict(Counter(str(len(r[2])) for r in evaluated))})
if __name__=="__main__":main()

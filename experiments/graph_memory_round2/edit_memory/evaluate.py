"""Join sealed predicted top-three indices to later accepted edits with a repository-cluster analysis."""
from collections import defaultdict, Counter
import csv
from experiment import HERE, rows, read, save, sha, np, gzip, packed
def main():
    for n,h in read("prediction_lock.json").items():assert sha((HERE/n).read_bytes())==h
    for n,h in read("method_lock.json").items():
        from pathlib import Path
        assert sha((HERE/Path(n)).read_bytes())==h
    instances=set(); allcuts=0; audited=[]; arms=["recent","base","flat","address","full","placebo"]
    for p in sorted(HERE.glob("predict_*.gz")):
        pred={(i,t):(prior,rankings) for i,t,prior,rankings in rows(p)}
        allcuts+=len(pred);instances.update(i for i,t in pred)
        for i,t,span,possible in rows(p.with_name(p.name.replace("predict","gold"))):
            prior,ranking=pred[(i,t)];score={}
            for arm in arms:
                top=ranking.get(arm,[])
                score[arm]=[int(bool(span) and span[0] in top[:1]),int(bool(span) and span[0] in top),int(bool(span) and set(span)<=set(top))]
            audited.append(dict(id=i,cut=t,repo=i.split(".")[0],history=prior,possible=possible,score=score))
    with gzip.open(HERE/"audited_outcomes.jsonl.gz","wt",encoding="utf8") as out:
        for r in audited:packed(out,r)
    def metrics(rs):
        projects=sorted({r["repo"] for r in rs})
        sums={a:np.sum([r["score"][a] for r in rs],axis=0).tolist() for a in arms}
        stats={}
        for a in arms:
            d=np.array([np.subtract(r["score"]["full"],r["score"][a]) for r in rs])
            clusters=np.array([d[[j for j,r in enumerate(rs) if r["repo"]==q]].sum(axis=0) for q in projects])
            counts=np.array([sum(r["repo"]==q for r in rs) for q in projects]);rng=np.random.default_rng(6639)
            boot=rng.integers(len(projects),size=(10000,len(projects)))
            effects=clusters[boot].sum(axis=1)/counts[boot].sum(axis=1)[:,None]
            stats[a]=dict(delta=(d.sum(axis=0)/len(rs)).tolist(),wins=(d==1).sum(axis=0).tolist(),losses=(d==-1).sum(axis=0).tolist(),
                         ci=np.quantile(effects,[.025,.975],axis=0).tolist(),repo_macro=(clusters/counts[:,None]).mean(axis=0).tolist(),
                         repo_positive=(clusters>0).sum(axis=0).tolist(),repo_negative=(clusters<0).sum(axis=0).tolist(),
                         projects={q:[int(n),*map(int,x)] for q,n,x in zip(projects,counts,clusters)})
        return dict(n=len(rs),projects=len(projects),instances=len({r['id'] for r in rs}),candidate_contains_start=sum(r['possible'] for r in rs),sums=sums,full_minus=stats)
    save("results.json",dict(metrics=["hit@1","hit@3","full_span@3"],cases=metrics(audited),
         after_edits=metrics([r for r in audited if r["history"]]),cuts=allcuts,seen_instances=len(instances)))
if __name__=="__main__":main()

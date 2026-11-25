"""Evaluate signed forecast intervals against independent future address/edit labels."""
from collections import Counter,defaultdict
from statistics import mean
import sys
import numpy as np
from predict import source,Tokenizer,tokenids
from common import *
def merge(spans):
    out=[]
    for a,b in sorted(spans):
        if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
        else:out.append([a,b])
    return out
def prep_rows(panel):
    pre="loc-" if panel=="loc" else ""
    seal=read(D/(pre+"forecast-seal.json"))
    assert sha(D/(pre+"forecasts.json.gz"))==seal["sha"]
    schema=read(D/(pre+"dataset.json"))
    assert sha(P/(pre+"gold.json.gz"))==schema["labels_sha"]
    truth={x["id"]:x for x in read(P/(pre+"gold.json.gz"))}
    obs={x["id"]:x for x in read(D/(pre+"observations.json.gz"))}
    tok=Tokenizer.from_file(str(T));tok.no_truncation();tok.no_padding()
    rows=[];removed=[];indices={}
    for f in read(D/(pre+"forecasts.json.gz")):
        uid=f["id"];key=f["file"];g=truth[uid]
        if key not in indices:
            lines=source(key).split("\n");e=[0]
            for line in lines:e.append(e[-1]+len(tokenids(tok,line)))
            indices[key]=(lines,e)
        lines,e=indices[key]
        if panel=="loc":
            target=sorted(map(int,g["lines"]))
            if any(i<1 or i>len(lines) or digest(lines[i-1])!=g["lines"][str(i)] for i in target):
                removed.append([uid,"deletion_mismatches_source"]);continue
        else:
            a,b=g["target"]
            if a>len(lines):removed.append([uid,"target_beyond_eof"]);continue
            target=list(range(a,min(b,len(lines))+1))
        target=[i for i in target if e[i]>e[i-1]]
        if not target:removed.append([uid,"empty_target"]);continue
        l,h=f["visible"]
        def hit(spans):return {i for i in target if any(a<=e[i-1] and e[i]<=b for a,b in spans)}
        old=hit([[l,h]]);fresh=set(target)-old
        methods={}
        for arm,c in [("base",dict(windows=[],cost=0))]+list(f["arms"].items())+[("equal_"+k,v) for k,v in f["equal"].items()]:
            windows=c["windows"];un=merge([[l,h]]+[[u[0],u[1]] for u in windows]);coverage=hit(un)
            methods[arm]=dict(covered=len(coverage),recall=len(coverage)/len(target),all=int(len(coverage)==len(target)),any=int(bool(coverage)),new_recall=len(coverage-old)/len(fresh) if fresh else None,newly_covered=len(coverage-old),tokens=c["cost"],ranges=len(windows))
        assert methods["equal_right"]["tokens"]==methods["equal_both"]["tokens"]
        rows.append(dict(id=uid,issue=f["issue"],repo=f["repo"],file=key,target_count=len(target),visible_tokens=h-l,initial=len(old),new=len(fresh),left=sum(e[i]<=l for i in target),right=sum(e[i-1]>=h for i in target),trajectory=obs[uid].get("trajectory"),methods=methods))
    return rows,removed
def summarize(rows,removed):
    byissue=defaultdict(list)
    for r in rows:byissue[r["issue"]].append(r)
    issueids=sorted(byissue);methods=rows[0]["methods"].keys()
    val=lambda x:mean(x) if x else None
    av={}
    for arm in methods:
        per={}
        for issue,rr in byissue.items():
            per[issue]={}
            for metric in rr[0]["methods"][arm]:
                values=[r["methods"][arm][metric] for r in rr if r["methods"][arm][metric] is not None]
                per[issue][metric]=val(values)
        av[arm]={k:val([r[k] for r in per.values() if r[k] is not None]) for k in next(iter(per.values()))}
    def deltas(a,b):
        out=[]
        for i in issueids:
            rr=byissue[i];out.append([i,rr[0]["repo"],mean(r["methods"][a]["recall"]-r["methods"][b]["recall"] for r in rr)])
        return out
    pairs=[("equal_both","equal_right"),("both","right"),("line_neighbors","both"),("scope_neighbors","line_neighbors"),("lexical","right")]
    if "index" in methods:pairs.append(("index","both"))
    diff={}
    for a,b in pairs:
        vec=deltas(a,b);v=np.array([x[2] for x in vec]);rng=np.random.default_rng(27027)
        sample=v[rng.integers(0,len(v),size=(10000,len(v)))].mean(axis=1)
        repos={s:mean(z[2] for z in vec if z[1]==s) for s in sorted({z[1] for z in vec})}
        diff[a+"__"+b]=dict(mean=float(v.mean()),ci=np.quantile(sample,[.025,.975]).tolist(),wins=int((v>0).sum()),losses=int((v<0).sum()),ties=int((v==0).sum()),per_repo=repos)
    return dict(rows=len(rows),issues=len(byissue),repos=dict(Counter(v[0]["repo"] for v in byissue.values())),files=len({r["file"] for r in rows}),trajectories=len({r["trajectory"] for r in rows if r["trajectory"]}),exclusions=removed,
                target_lines=sum(r["target_count"] for r in rows),new_lines=sum(r["new"] for r in rows),left_lines=sum(r["left"] for r in rows),right_lines=sum(r["right"] for r in rows),
                opportunities=sum(r["new"]>0 for r in rows),initially_complete=sum(r["new"]==0 for r in rows),initially_absent=sum(r["initial"]==0 for r in rows),
                initial_tokens_mean=mean(mean(r["visible_tokens"] for r in group) for group in byissue.values()),outcomes=av,contrasts=diff)
def main(panel):
    pre="loc-" if panel=="loc" else "";rows,removed=prep_rows(panel)
    save(D/(pre+"per-case.json.gz"),rows)
    res=summarize(rows,removed);save(D/(pre+"results.json"),res)
    print(panel,{k:res[k] for k in ('rows','issues','repos','opportunities')},res["contrasts"]["equal_both__equal_right"],{k:round(v["recall"],3) for k,v in res["outcomes"].items()})
if __name__=="__main__":main(sys.argv[1])


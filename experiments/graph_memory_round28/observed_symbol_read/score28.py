"""Open original patch column only after both forecast seals exist and source files are fixed."""
from collections import Counter,defaultdict
from statistics import mean,median
import re,sys
import numpy as np
import pyarrow.parquet as pq
from tokenizers import Tokenizer
from common28 import *
from prepare import prod
from predict28 import text_of
def labels(patch):
    targets=defaultdict(dict);path=None;old=None
    for line in patch.split("\n"):
        if line.startswith("diff --git "):path=None;old=None
        elif old is None and line.startswith("--- "):path=line[6:] if line.startswith("--- a/") else None
        elif line.startswith("@@ "):
            m=re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@",line)
            old=int(m[1]) if m and path and prod(path) else None
        elif old is not None and line.startswith("-"):
            if line[1:].strip():targets[path][old]=line[1:].rstrip("\r")
            old+=1
        elif old is not None and line.startswith(" "):old+=1
    return targets
def summary(rows,unscorable,pred):
    arms=list(rows[0]["out"]);metrics={}
    for a in arms:
        x=[r["out"][a] for r in rows]
        metrics[a]={k:mean([v[k] for v in x if v[k] is not None]) if any(v[k] is not None for v in x) else None for k in x[0]}
        metrics[a]["all_selected_zeros"]=sum(v["recall"] for v in x)/(len(rows)+len(unscorable))
    contrasts={};repo=sorted({r["repo"] for r in rows});groups=[[i for i,r in enumerate(rows) if r["repo"]==k] for k in repo]
    for a in arms:
        if a in ("base","repeat_bm25","eq_repeat_bm25"):continue
        b="eq_repeat_bm25" if a.startswith("eq_") else "repeat_bm25"
        v=np.array([r["out"][a]["recall"]-r["out"][b]["recall"] for r in rows])
        rng=np.random.default_rng(28028);ix=rng.integers(0,len(v),(10000,len(v)));samples=v[ix].mean(axis=1)
        ixr=rng.integers(0,len(groups),(10000,len(groups)));s=np.array([v[j].sum() for j in groups]);n=np.array(list(map(len,groups)))
        cb=s[ixr].sum(axis=1)/n[ixr].sum(axis=1)
        contrasts[a]=dict(mean=v.mean(),ci=np.quantile(samples,[.025,.975]).tolist(),repo_ci=np.quantile(cb,[.025,.975]).tolist(),wins=int((v>0).sum()),losses=int((v<0).sum()),ties=int((v==0).sum()),by_repo={k:float(v[g].mean()) for k,g in zip(repo,groups)},leave_repo_out={k:float((v.sum()-v[g].sum())/(len(v)-len(g))) for k,g in zip(repo,groups)} )
    timings={k:[sum(r["timing"][k] for r in pred)*1e-9,median(r["timing"][k] for r in pred)*1e-6] for k in pred[0]["timing"]}
    strata={}
    for condition in ("edge","no_edge","target_in_file","target_elsewhere"):
        sel=[r for r in rows if dict(edge=r["edge"],no_edge=not r["edge"],target_in_file=r["infile"]>0,target_elsewhere=not r["infile"])[condition]]
        strata[condition]=dict(n=len(sel),gain=mean(r["out"]["eq_query_call"]["recall"]-r["out"]["eq_repeat_bm25"]["recall"] for r in sel) if sel else None)
    return dict(scored=len(rows),repositories=Counter(r["repo"] for r in rows),unscorable=unscorable,total_gold=sum(r["target"] for r in rows),file_gold=sum(r["infile"] for r in rows),target_in_file=sum(r["infile"]>0 for r in rows),outcomes=metrics,contrasts=contrasts,strata=strata,
            forecast_count=len(pred),measured_timing_total_sec_median_ms=timings,edge_all=sum(r["info"]["edge"] for r in pred),ambiguous_fragment_lexer=sum(r["info"]["partial_lexer"] for r in pred),mean_initial_tokens=mean(r["visible"][1]-r["visible"][0] for r in pred))
def main(panel):
    checks()
    for pg in ("swe","loc"):
        seal=read(D/(pg+"-seal.json"))
        assert seal["forecasts"]==sha(D/(pg+"-forecasts.json.gz")) and seal["operators"]==sha(D/"operators.py") and seal["runner"]==sha(D/"predict28.py")
    pqpath=V if panel=="swe" else B
    tbl=pq.read_table(pqpath,columns=["instance_id","patch"]);offset={q:i for i,q in enumerate(tbl["instance_id"].to_pylist())}
    inp={r["issue"]:r for r in read(D/(panel+"-inputs.json.gz"))}
    pred=sorted(read(D/(panel+"-forecasts.json.gz")),key=lambda r:r["issue"])
    tok=Tokenizer.from_file(str(T));tok.no_truncation();tok.no_padding();rows=[];unscorable=[];errors=[]
    for f in pred:
        q=f["issue"];path=inp[q]["path"];raw=tbl["patch"][offset[q]].as_py()
        targets=labels(raw);total=sum(len(v) for v in targets.values())
        if not total:unscorable.append(q);continue
        lines=text_of(f["file"]).split("\n");e=[0]
        for line in lines:e.append(e[-1]+len(tok.encode(line,add_special_tokens=False).ids))
        goal=targets.get(path,{})
        if any(i>len(lines) or i<1 or lines[i-1]!=s or e[i]==e[i-1] for i,s in goal.items()):
            errors.append(q);continue
        l,h=f["visible"]
        def hits(span):
            windows=[(l,h)]+([tuple(span)] if span else [])
            windows.sort()
            if len(windows)>1 and windows[1][0]<=windows[0][1]:windows=[(windows[0][0],max(x[1] for x in windows))]
            return sum(any(a<=e[i-1] and e[i]<=b for a,b in windows) for i in goal)
        base=hits([]);out={}
        for k,c in [("base",dict(span=[],cost=0))]+list(f["arms"].items())+[("eq_"+k,c) for k,c in f["equal"].items()]:
            n=hits(c["span"]);out[k]=dict(recall=n/total,within=n/len(goal) if goal else None,any=int(n>0),all=int(n==total),added=n-base,hit=n,cost=c["cost"])
        assert out["eq_query_call"]["cost"]==out["eq_repeat_bm25"]["cost"]
        rows.append(dict(issue=q,repo=f["repo"],target=total,infile=len(goal),edge=f["info"]["edge"],out=out))
    res=summary(rows,unscorable,pred);res["mismatch_or_unrepresented"]=errors
    save(D/(panel+"-outcomes.json.gz"),rows);save(D/(panel+"-results.json"),res)
    print(panel,res["scored"],res["target_in_file"],res["edge_all"],"no-target",len(unscorable),"bad",errors)
    print(panel,res["contrasts"]["eq_query_call"])
if __name__=="__main__":main(sys.argv[1])


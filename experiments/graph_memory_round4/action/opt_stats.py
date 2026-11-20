"""Summarize the sealed recovery policy including all additional requests and strict payload caps."""
from collections import Counter
from itertools import product
from pathlib import Path
import platform
import numpy as np
from experiment import D,read,rows,write

METHODS=("full","pages","adapt_flat","adapt_joint","rolling256","optim")
def analyze(p):
    rr=[row for j in range(8) for row in rows(D/f"opt_cost_{p}_{j}.jsonl.gz")]
    names=sorted({r[1] for r in rr});tags=np.array([r[1] for r in rr]);issue=np.array([r[0] for r in rr]);clusters=[tags==nm for nm in names]
    ns=np.array([g.sum() for g in clusters]);inds=np.random.default_rng(811426).integers(len(ns),size=(10000,len(ns)));n=ns[inds].sum(axis=1)
    sums=np.array([[r[3][m] for r in rr] for m in METHODS])
    metrics={}
    for m,q in zip(METHODS,sums):
        wire=q[:,0];metrics[m]=dict(bytes=int(wire.sum()),mean=float(wire.mean()),median=float(np.median(wire)),p95=float(np.quantile(wire,.95)),request=int(q[:,1].sum()),reply=int(q[:,2].sum()),round_trips=int(q[:,3].sum()),within={k:int(sum(wire<=k)) for k in [512,1024,2048,4096]})
    retries=sum(r[7] for r in rr);added=sum(r[10] for r in rr if r[7]);comp={}
    for m,q in zip(METHODS,sums):
        d=q[:,0]-sums[-1,:,0];gs=np.array([d[g].sum() for g in clusters]);b=gs[inds].sum(axis=1)/n;sum0=metrics[m]["bytes"]
        comp[m]=dict(saved=int(d.sum()),saved_percent=100*float(d.sum())/sum0,saved_per_view=float(d.mean()),ci=np.quantile(b,[.025,.975]).tolist(),
          equal_project=float(np.mean(gs/ns)),equal_issue=float(np.mean([np.mean(d[issue==i]) for i in sorted(set(issue))])),
          wins=int(sum(d>0)),losses=int(sum(d<0)),ties=int(sum(d==0)),per_project={nm:[int(nr),int(y)] for nm,nr,y in zip(names,ns,gs)},
          p_exact_two_sided=float(np.mean([abs(np.array(sign)@gs)>=abs(d.sum()) for sign in product((-1,1),repeat=len(ns))])),
          break_even_extra_bytes_per_RTT=float(d.sum()/retries) if retries else None)
    return dict(issues=len(set(issue)),repos=len(ns),views=len(rr),output_lines=sum(r[4] for r in rr),views_with_resident_rows=sum(bool(r[5]) for r in rr),optim_reply=sum(r[9] for r in rr),rereads=retries,extra_bytes_reread=added,
                injected_stale_detected=sum(r[8] for r in rr),methods=metrics,optim_minus=comp)
if __name__=="__main__":
    res={p:analyze(p) for p in ("A","B","C")};write(D/"opt_results.json",res)
    for p,r in res.items():
        print(p,r["views"],r["repos"],r["rereads"],[(k,r["methods"][k]["bytes"]) for k in METHODS])
        print(r["optim_minus"]["adapt_flat"])


"""Paired analysis with one deterministic resample per issue shared across treatments."""
import numpy as np
from rec_data import *
D=HERE;save=store_file

COMPARE=(("joint_8192","views_8192"),("joint_unlimited","views_unlimited"),("receipts_8192","views_8192"),("joint_2048","views_2048"))
def subset(rows,pred):
    names=sorted(rows[0][1]["arms"])
    groups=sorted({row["issue"] for k,row in rows})
    positions={g:i for i,g in enumerate(groups)}
    rng=np.random.default_rng(441071);n=len(groups)
    weights=rng.multinomial(n,np.repeat(1/n,n),size=10000)
    result={};contrasts={}
    for m in names:
        sizes=np.array([pred[k]["arms"][m]["wire"][:4] for k,r in rows],dtype=int)
        slots=dict(wire=int(sizes[:,0].sum()),wire_p50=float(np.median(sizes[:,0])),wire_p95=float(np.percentile(sizes[:,0],95)),
             wire_max=int(sizes[:,0].max()),refs=int(sizes[:,1].sum()),bodies=int(sizes[:,2].sum()),body_bytes=int(sizes[:,3].sum()))
        for out in ("read","all"):
            agg=Counter()
            for k,r in rows:agg.update(r["arms"][m][out])
            slots[out]=dict(agg)
        result[m]=slots
    for m,b in COMPARE:
        pair=m+"_minus_"+b;compar={}
        for out in ("read","all"):
            num=np.zeros(n);den=np.zeros(n);wins=loss=0;lo=hi=0
            for k,r in rows:
                d=r["arms"][m][out]["hit"]-r["arms"][b][out]["hit"]
                ii=positions[r["issue"]];num[ii]+=d;den[ii]+=1;wins+=d>0;loss+=d<0
                if pair in r["paired_bounds"]:
                    l,u=r["paired_bounds"][pair][out];lo+=l;hi+=u
            means=num/den
            micro=100*(weights@num)/(weights@den);macro=100*(weights@means)/n
            compar[out]=dict(win=wins,lose=loss,micro=100*num.sum()/den.sum(),macro=100*means.mean(),
                macro_ci=np.quantile(macro,[.025,.975]).tolist(),micro_ci=np.quantile(micro,[.025,.975]).tolist(),
                censor_bound_micro=[100*lo/len(rows),100*hi/len(rows)] if pair in rows[0][1]["paired_bounds"] else None)
        contrasts[pair]=compar
    return dict(edits=len(rows),issues=n,repos=len({r["repo"] for k,r in rows}),runs=len({r["run"] for k,r in rows}),
        closed=sum(r["closed"] for k,r in rows),views=sum(r["views"] for k,r in rows),with_views=sum(r["views"]>0 for k,r in rows),
        with_novel=sum(r["demand"] for k,r in rows),novel_occurrences=sum(r["demand_lines"] for k,r in rows),
        arms=result,contrasts=contrasts)
def main():
    outcome=read(D/"outcomes.json.gz");pred=read(D/"forecasts.json.gz");assert set(outcome)==set(pred)
    ix={"all":lambda r:True,"held":lambda r:r["held"],"main":lambda r:r["group"]=="main","closed":lambda r:r["closed"],
        "observable":lambda r:r["demand"],"held_closed":lambda r:r["held"] and r["closed"]}
    save("summary.json",{s:subset([(k,r) for k,r in outcome.items() if test(r)],pred) for s,test in ix.items()})
if __name__=="__main__":main()

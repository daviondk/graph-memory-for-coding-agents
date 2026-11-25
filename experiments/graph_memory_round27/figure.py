"""Plot measured cumulative index cost and four-worker RPC latency from released receipts."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
from statistics import median
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
def load(name):
    p=HERE/name;data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix==".gz" else data)

def deltas(name):
    measurements=defaultdict(list)
    for rep,corpus,episode,method,ingest,queries in load(name):
        if corpus!="squad" or method not in ("raw","eager"):
            continue
        total=ingest
        for i in range(len(queries)+1):
            if i:
                total+=queries[i-1][1]
            measurements[episode,method,i].append(total/1e6)
    ids=sorted({k[0] for k in measurements})
    return np.array([[median(measurements[s,"eager",i])-median(measurements[s,"raw",i]) for i in range(12)] for s in ids])

def main():
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(1,2,figsize=(11.4,4.2),layout="constrained")
    a,b=axes;x=np.arange(12)
    for file,label,color,style in (("times.json.gz","First measurement","#006D77","-"),("promotion-times.json.gz","Repeated controls","#9D4D22","--")):
        table=deltas("write_cost/"+file)
        rng=np.random.default_rng(27719)
        samples=table[rng.integers(0,len(table),size=(12000,len(table)))].mean(axis=1)
        lo,hi=np.quantile(samples,[.025,.975],axis=0)
        a.fill_between(x,lo,hi,color=color,alpha=.12,linewidth=0)
        a.plot(x,table.mean(axis=0),label=label,color=color,linestyle=style,marker="o",markersize=3.5)
    a.axhline(0,color="#424242",linewidth=.9);a.set(xticks=range(0,12),xlabel="Subsequent questions per article",ylabel="Index minus raw-scan cumulative time (ms)")
    a.set_title("A   When does indexing pay off?",loc="left",fontweight="bold",fontsize=12)
    a.legend(frameon=False,loc="lower left")
    stats=load("worker_cache/results.json")
    cases=[("raw_cache/4/affine","Full cache · fixed"),("raw_cache/4/rotate","Full cache · rotating"),("shared_sql/4/affine","Shared index · fixed"),
           ("shared_sql/4/rotate","Shared index · rotating"),("term_cache/4/affine","Term cache · fixed"),("term_cache/4/rotate","Term cache · rotating")]
    for y,(k,label) in enumerate(cases):
        r=stats[k];lo=r["p50_rpc_us"];hi=r["p95_rpc_us"];color="#006D77" if k.endswith("affine") else "#9D4D22"
        b.hlines(y,lo,hi,color=color,lw=1.6)
        b.scatter([lo],[y],color=color,s=28,zorder=3)
        b.scatter([hi],[y],facecolor="white",edgecolor=color,s=28,zorder=3)
    b.set_yticks(np.arange(len(cases)),[label for k,label in cases]);b.invert_yaxis();b.set_xlim(0,1080)
    b.set_xlabel("Round-trip latency (µs)")
    b.set_title("B   Moving reads between four workers",loc="left",fontweight="bold",fontsize=12)
    b.plot([],[],"o",color="#414141",label="Median");b.plot([],[],"o",markerfacecolor="white",markeredgecolor="#414141",label="95th percentile")
    b.legend(frameon=False,loc="lower right",fontsize=9)
    for ax in axes:
        ax.grid(axis="x" if ax==b else "y",color="#dbdfe0",alpha=.65,lw=.7);ax.set_axisbelow(True)
    fig.savefig(HERE/"memory-costs.png",dpi=190,bbox_inches="tight",facecolor="white")
    plt.close(fig)
if __name__=="__main__":
    main()


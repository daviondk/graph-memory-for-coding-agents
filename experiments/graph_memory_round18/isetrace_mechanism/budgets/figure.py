"""Figure of BM25 evidence selection at the official token budgets; cluster by trajectory."""
import gzip
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

ROOT=Path(__file__).resolve().parent
stats=json.loads((ROOT/"summary.json").read_bytes())
rows=json.loads(gzip.decompress((ROOT/"outcomes.json.gz").read_bytes()))
by_query={(r["q"],r["arm"]):r for r in rows}
tids=sorted({r["t"] for r in rows})
pos={t:i for i,t in enumerate(tids)}
grid=stats["budgets"]
totals=np.zeros((len(tids),7),dtype=int)
for r in rows:
    if r["arm"]!="provenance.related":
        continue
    control=by_query[r["q"],"provenance.value"]
    arr=totals[pos[r["t"]]]
    arr[:6]+=np.asarray(r["fs"])-np.asarray(control["fs"])
    arr[6]+=1
rng=np.random.default_rng(13)
samples=[]
for _ in range(100):
    bs=totals[rng.integers(len(tids),size=(100,len(tids)))].sum(axis=1)
    samples.append(100*bs[:,:6]/bs[:,6,None])
lo,hi=np.quantile(np.concatenate(samples),[.025,.975],axis=0)
point=100*totals[:,:6].sum(axis=0)/totals[:,6].sum()
(ROOT/"budget-intervals.json").write_text(json.dumps({"budgets":grid,"difference_pp":point.tolist(),"ci_pointwise95":[lo.tolist(),hi.tolist()]},indent=2)+"\n",encoding="utf8")
plt.rcParams.update({"font.family":"DejaVu Sans","axes.spines.top":False,"axes.spines.right":False,
                     "font.size":10,"figure.facecolor":"white","axes.facecolor":"white","axes.edgecolor":"#A8B2B8",
                     "axes.labelcolor":"#213442","xtick.color":"#324653","ytick.color":"#324653"})
fig,(main,gain)=plt.subplots(2,1,figsize=(8.1,6.3),sharex=True,gridspec_kw={"height_ratios":[1.45,1]})
fig.subplots_adjust(left=.13,right=.96,top=.88,bottom=.14,hspace=.36)
fig.suptitle("Полнота доказательств при разных бюджетах памяти",y=.975,fontsize=15,x=.53,fontweight="semibold")
x=np.arange(6)
for policy,label,color,marker,ls in [
    ("flat.prefix","Плоский BM25, префикс","#86959C","v",":"),
    ("provenance.prefix","Узлы вызова, префикс","#495768","s","--"),
    ("provenance.value","Добор по стоимости","#BB661A","^","-"),
    ("provenance.related","Добор по связи вызова","#087D78","o","-")]:
    main.plot(x,100*np.array(stats["means"][policy]["fs"]),color=color,marker=marker,linestyle=ls,label=label,linewidth=1.85,markersize=5)
main.set_ylabel("Full Support, %")
main.set_ylim(-4,91)
main.set_yticks([0,20,40,60,80])
main.grid(axis="y",alpha=.2)
main.legend(loc="upper left",ncol=2,frameon=False,fontsize=8.6,columnspacing=1.4)
gain.axhline(0,color="#7B878E",lw=1,ls="--")
gain.errorbar(x,point,yerr=[point-lo,hi-point],fmt="o-",color="#087D78",ecolor="#507974",capsize=4,linewidth=1.6,markersize=5)
gain.set_ylabel("Связь минус стоимость, п.п.")
gain.set_ylim(min(lo)-.65,max(hi)+.7)
gain.yaxis.set_major_locator(MaxNLocator(5,integer=True))
gain.grid(axis="y",alpha=.18)
gain.set_xlabel("Бюджет чтения, токены")
gain.set_xticks(x,[f"{b:,}".replace(","," ") for b in grid])
fig.text(.13,.035,"2 000 запросов, 1 207 траекторий ISETrace. Планки — поточечные 95% кластерные интервалы.",fontsize=9,color="#53616B")
fig.savefig(ROOT/"budget-curve.png",dpi=170)


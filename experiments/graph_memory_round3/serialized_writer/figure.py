"""Render the measured full-checkpoint capacity curve from sealed results. Matplotlib 3.10.7."""
from pathlib import Path
import json,os,sys
D=Path(__file__).resolve().parent
local=D.parent/".plotlibs"
if local.exists():sys.path.insert(0,str(local))
os.environ.setdefault("MPLCONFIGDIR",str(D.parent/".plotcache/mpl"))
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
r=json.loads((D/"curve_results.json").read_bytes());sizes=np.array([1,2,4,8,12,24]);n=r["n"];x=np.log2(sizes)
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False,"pdf.fonttype":42})
fig,(a,b)=plt.subplots(1,2,figsize=(10,4.45),gridspec_kw={"width_ratios":[1.12,1]},layout="constrained")
for c,label,col,mark in [("typed","Связные фрагменты","#225f82","o"),("point","Отдельные страницы","#a05d28","s"),("lru","По давности (LRU)","#6a6d71","^")]:
    y=[100*r["curves"][f"{c}@{int(k)*1024}"]["hits"]/n for k in sizes]
    a.plot(x,y,color=col,marker=mark,ms=4.8,lw=1.8,label=label)
a.axhline(100*r["gold_in_unbounded_memory"]/n,color="#888",ls=":",lw=1)
a.text(.15,69.1,"Потолок наблюдаемой истории",color="#555",fontsize=8.4)
a.set(ylabel="Целиком сохранённые правки, %",ylim=(17,74),title="Доступность текста следующей правки");a.legend(frameon=False,fontsize=9,loc="lower right")
for comp,dx,label,col,mark in [("point",-.045,"К оценке отдельных страниц","#225f82","o"),("lru",.045,"К вытеснению по давности","#6a6d71","^")]:
    cr=[r["comparisons"][f"typed-{comp}@{int(k)*1024}"] for k in sizes]
    y=np.array([c["delta"][0]*100 for c in cr]);intervals=np.array([[c["ci"][0][0]*100 for c in cr],[c["ci"][1][0]*100 for c in cr]])
    b.errorbar(x+dx,y,yerr=np.vstack((y-intervals[0],intervals[1]-y)),fmt=mark,color=col,markersize=4.5,capsize=3,linewidth=1.3,label=label)
b.axhline(0,color="#888",lw=1);b.set(ylabel="Разность, процентные пункты",ylim=(-1.7,11.5),title="Выигрыш связной памяти и 95% ДИ");b.legend(frameon=False,fontsize=8.4,loc="upper right")
for ax in (a,b):
    ax.set_xticks(x,[str(i) for i in sizes]);ax.set_xlabel("Предел сериализованного состояния, КиБ");ax.grid(axis="y",linewidth=.5,alpha=.3);ax.set_axisbelow(True);ax.tick_params(length=3,color="#777")
fig.suptitle("Бюджет рабочей памяти на 1 210 действиях в 12 проектах",fontsize=14,fontweight="bold")
for suf in ("png","pdf"):fig.savefig(D/("capacity-curve."+suf),dpi=180,bbox_inches="tight")



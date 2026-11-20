from pathlib import Path
import json,sys,statistics
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parents[1]/"graph_memory_round3/.plotlibs"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
rows=[json.loads(x) for x in (R.parent/"latency/times_native.jsonl").read_text().splitlines()]
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9})
fig,ax=plt.subplots(figsize=(6.1,2.55))
for typ,color,mark,name in [(False,"#bf683e","x","Нужен архив"),(True,"#006e78","o","Диапазон целиком в кеше")]:
    sel=[r for r in rows if r["hot"]==typ]
    ax.scatter([statistics.median(r["us"]["archive"])/1000 for r in sel],[statistics.median(r["us"]["routed"])/1000 for r in sel],s=14,marker=mark,alpha=.68,color=color,linewidths=.8,label=name)
ax.set(xscale="log",yscale="log",xlabel="Только архив, мс",ylabel="Кеш + архив, мс",xlim=(.0017,32),ylim=(.002,32))
ax.plot([.002,30],[.002,30],"--",linewidth=.8,color="#52616c")
ax.set_xticks([.01,.1,1,10]);ax.set_yticks([.01,.1,1,10])
for axis in (ax.xaxis,ax.yaxis):axis.set_major_formatter(FuncFormatter(lambda v,p:format(v,"g").replace(".",",")))
ax.grid(which="major",alpha=.18);ax.legend(loc="upper left",frameon=False,fontsize=8.5)
for s in ("top","right"):ax.spines[s].set_visible(False)
fig.tight_layout();fig.savefig(R/"latency.png",dpi=220);plt.close(fig)


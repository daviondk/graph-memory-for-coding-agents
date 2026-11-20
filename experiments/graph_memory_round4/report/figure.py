"""Paired experiments in the same 320 Java tasks. Preserve native CIs with repository resampling."""
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/"graph_memory_round3/.plotlibs"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
read=lambda p:json.loads((HERE.parent/p).read_bytes())
h=read("repo/holdout_results.json")["paired"]
b=read("java_reader/B_results.json")["all"]["graph_minus_semlith"]["em"]
rows=[]
for width in ("3","10"):
    c=h[width]["contrasts"]["graph-binary"]
    for i,k in ((0,"Первое место"),(2,"В первой пятёрке")):
        rows.append((f"{k} · {width} стр.",c["delta"][i]*100,c["ci"][0][i]*100,c["ci"][1][i]*100))
rows.append(("Точная строка Qwen · 3 стр.",b["delta"]*100,b["ci"][0]*100,b["ci"][1]*100))
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"axes.spines.right":False,"axes.spines.top":False})
fig,ax=plt.subplots(figsize=(8,3.0))
fig.subplots_adjust(left=.42,right=.96,bottom=.23,top=.98)
ax.axvline(0,color="#566667",lw=.9)
for j,(_,point,lo,hi) in enumerate(rows):
    ax.errorbar(point,j,xerr=[[max(0,point-lo)],[max(0,hi-point)]],color=("#923f28" if j==4 else "#285263"),fmt="o",capsize=4,lw=1.7)
ax.set_yticks(range(len(rows)),[x[0] for x in rows]);ax.set_ylim(4.55,-.55)
ax.set_xlabel("Разница граф − Semlith, процентные пункты")
ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f"{x:+g}" if x else "0"))
ax.tick_params(axis="y",length=0,pad=9);ax.spines["left"].set_visible(False);ax.grid(axis="x",color="#d7dcdc",lw=.6);ax.set_axisbelow(True)
fig.savefig(HERE/"paired-outcomes.png",dpi=190,facecolor="white");plt.close(fig)


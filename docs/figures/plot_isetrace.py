"""Render the five-seed ISETrace comparison from the released per-question data."""
import gzip
import json
from pathlib import Path
import os
os.environ.setdefault("SOURCE_DATE_EPOCH","0")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

HERE=Path(__file__).resolve().parent
DATA=HERE.parents[1]/"experiments"/"graph_memory_round32"/"isetrace_five_seeds"
TEAL="#086b61"
SLATE="#5e6873"

def main():
    report=json.loads((DATA/"results.json").read_bytes())
    data=json.loads(gzip.decompress((DATA/"per-query.json.gz").read_bytes()))
    metric=data["metrics"].index("full_support_2048")
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"pdf.fonttype":42,"svg.fonttype":"none","svg.hashsalt":"ISETrace paired graph"})
    fig,(left,right)=plt.subplots(1,2,figsize=(9.2,3.9))
    fig.subplots_adjust(left=.10,right=.98,top=.77,bottom=.26,wspace=.54)
    fig.suptitle("Adding a structural prior to the same dense encoder",x=.065,y=.97,ha="left",fontsize=15,weight="bold")
    for ax in [left,right]:
        ax.grid(axis="x",color="#e1e5e7",linewidth=.7)
        ax.set_axisbelow(True)
        ax.spines[["top","left","right"]].set_visible(False)
        ax.spines["bottom"].set_color("#aeb6b9")
        ax.tick_params(axis="y",length=0,pad=7)
    seeds=report["seeds"]
    for i,s in enumerate(seeds):
        pairs=[[r[3][metric],r[4][metric]] for r in data["rows"] if r[0]==s]
        x,y=np.mean(pairs,axis=0)*100
        left.plot([x,y],[i,i],color="#b4c9c5",linewidth=2)
        left.scatter(x,i,s=45,color=SLATE,zorder=3)
        left.scatter(y,i,s=52,color=TEAL,marker="D",zorder=3)
    left.set(yticks=range(5),yticklabels=[f"Seed {s}" for s in seeds],ylim=(4.6,-.6),xlim=(71.4,80),xticks=[72,74,76,78,80],xlabel="Full Support@2048 (%)")
    left.set_title("Full support in each paired run",loc="left",fontsize=11,weight="bold",pad=10)
    labels=["Full Support@2048","Coverage@2048","Recall@5","MRR"]
    keys=["full_support_2048","coverage_2048","recall_5","mrr"]
    right.axvline(0,color=SLATE,lw=.9)
    for i,k in enumerate(keys):
        m,lo,hi=np.array(report["paired"][k])*100
        right.errorbar(m,i,xerr=[[m-lo],[hi-m]],fmt="o",color=TEAL,elinewidth=2,capsize=3,markersize=6)
        right.text(hi+.18,i,f"{m:+.2f}",va="center",fontsize=9,color="#314344")
    right.set(yticks=range(4),yticklabels=labels,ylim=(3.6,-.6),xlim=(-.4,10.4),xticks=[0,2,4,6,8,10],xlabel="Paired difference (percentage points)")
    right.set_title("Gain and 95% interval",loc="left",fontsize=11,weight="bold",pad=10)
    fig.legend(handles=[Line2D([0],[0],marker="o",color=SLATE,lw=0,label="Dense-FT"),Line2D([0],[0],marker="D",color=TEAL,lw=0,label="Dense-FT + graph prior")],loc="upper left",bbox_to_anchor=(.065,.92),frameon=False,ncol=2,handlelength=1.0,borderpad=0)
    fig.text(.065,.055,"ISETrace test split · 2,000 questions in 1,207 trajectories · five training seeds. Intervals resample whole trajectories.",fontsize=9,color="#435056")
    fig.savefig(HERE/"isetrace-five-seeds.pdf",metadata={"CreationDate":None,"ModDate":None})
    fig.savefig(HERE/"isetrace-five-seeds.svg",metadata={"Date":None})
    if "PLOT_CHECK_PNG" in os.environ:fig.savefig(os.environ["PLOT_CHECK_PNG"],dpi=110)
    plt.close(fig)
if __name__=="__main__":main()

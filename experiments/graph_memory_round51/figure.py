"""Create the interval plot directly from the four matched ranker panels."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parent

def load_results():
    b=ROOT/"baseline"
    panels=json.loads((b/"complete-results.json").read_bytes())
    panels["confirmed"]=json.loads((b/"confirm/results.json").read_bytes())
    return panels

def main():
    panels=load_results()
    rows=[("adaptive_address","2Wiki · earlier","640"),("gate_confirmation","2Wiki · confirmation","1,280"),
          ("hotpot","HotpotQA · transfer","640"),("confirmed","HotpotQA · confirmation","1,280")]
    fig,ax=plt.subplots(figsize=(8.0,3.6),layout="constrained")
    cols=[("graph-hybrid","#195c52","o","vs. trained lexical–dense hybrid"),
          ("graph-linked","#845c39","s","vs. always follow a mention")]
    for j,(key,label,n) in enumerate(rows):
        for off,(arm,color,marker,name) in zip((.13,-.13),cols):
            result=panels[key]["contrasts"][arm]["f1"]
            effect=result["delta_pp"]; lo,hi=result["ci95_pp"]
            ax.errorbar(effect,3-j+off,xerr=[[effect-lo],[hi-effect]],marker=marker,capsize=3,
                        markersize=5,elinewidth=1.4,color=color)
    ax.axvline(0,color="#68726c",lw=.9);ax.yaxis.grid(True,alpha=.18);ax.set_axisbelow(True)
    ax.set_yticks(range(3,-1,-1),[f"{label}  (n={n})" for _,label,n in rows])
    ax.set_xlabel("Difference in Answer F1, percentage points (paired 95% interval)")
    ax.set_title("Answer quality of the learned graph ranker",loc="left",fontsize=13)
    ax.spines[["right","top","left"]].set_visible(False);ax.tick_params(axis="y",length=0)
    handles=[Line2D([],[],marker=m,color=c,lw=1.4,label=label) for _,c,m,label in cols]
    ax.legend(handles=handles,loc="upper center",bbox_to_anchor=(.5,-.24),ncol=2,frameon=False,fontsize=8)
    ax.set_ylim(-.5,3.5)
    for ext in ("pdf","png"):
        kw={"metadata":{"CreationDate":None,"ModDate":None}} if ext=="pdf" else {"dpi":190}
        fig.savefig(ROOT/("ranker-comparisons."+ext),**kw)
    plt.close(fig)

if __name__=="__main__":
    main()


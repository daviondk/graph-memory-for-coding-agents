"""Render concentration and quality sensitivity from the per-history analysis."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
D=Path(__file__).resolve().parent
panels=json.loads((D/"results.json").read_bytes())["panels"]
keys=["0","0.01","0.05","0.1"]
positions=list(range(4))
labels=["All histories","Trim 1%","Trim 5%","Trim 10%"]
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"pdf.fonttype":42})
fig,(a,b)=plt.subplots(1,2,figsize=(9.5,3.6),gridspec_kw={"width_ratios":[1,1.2]},layout="constrained")
for i,k in enumerate(keys):
    row=panels[k]
    share=100*row["pooled_graph_share"]
    a.barh(i,share,color="#237b79",height=.52)
    a.barh(i,100-share,left=share,color="#b5c1c8",height=.52)
    a.text(share-1.7,i,f"{share:.1f}%",ha="right",va="center",color="white",fontweight="bold",fontsize=9)
    v=row["q_effect"];lo,hi=row["q_ci"]
    b.errorbar(v,i,xerr=[[v-lo],[hi-v]],fmt="o",markersize=6,capsize=4,color="#20466e")
    b.text(hi+.07,i,str(row["questions"]),va="center",fontsize=9,color="#43515f")
a.set_xlim(0,100);a.set_xticks([0,25,50,75,100]);a.xaxis.set_major_formatter(PercentFormatter(100))
a.set_yticks(positions,labels);b.set_yticks(positions,[])
for ax in (a,b):
    ax.set_ylim(3.55,-.55);ax.spines[["right","top","left"]].set_visible(False);ax.tick_params(axis="y",length=0)
    ax.grid(axis="x",color="#dce3e8",lw=.65);ax.set_axisbelow(True)
a.set_title("A   Excess edges at the halfway point",loc="left",fontsize=11,fontweight="bold")
a.set_xlabel("Share of excess fragment edges")
a.legend(["Never simultaneously valid","Previously valid"],loc="upper center",bbox_to_anchor=(.48,-.22),ncol=2,frameon=False,fontsize=8)
b.axvline(0,color="#303b45",lw=1);b.set_xlim(-.35,4.1);b.set_xticks([0,1,2,3,4]);b.set_xlabel("Change in full support at 2,048 tokens (pp)")
b.set_title("B   Materialized history vs. logical history",loc="left",fontsize=11,fontweight="bold")
b.text(.02,-.26,"Paired 95% intervals; labels give eligible questions.",transform=b.transAxes,fontsize=8,color="#43515f")
for suffix in ("png","pdf"):fig.savefig(D/f"trajectory-sensitivity.{suffix}",dpi=180,bbox_inches="tight")


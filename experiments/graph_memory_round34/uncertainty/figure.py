"""Rebuild the article figure from the checked crossed-bootstrap estimates."""
import os,json
from pathlib import Path
os.environ.setdefault("SOURCE_DATE_EPOCH","0")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
HERE=Path(__file__).resolve().parent
def main():
    d=json.loads((HERE/"results.json").read_bytes())["contrasts"];budgets=[256,512,1024,2048,4096,8192]
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"pdf.fonttype":42})
    fig,(a,b)=plt.subplots(1,2,figsize=(10,3.8),gridspec_kw={"width_ratios":[1,1.28]})
    fig.subplots_adjust(left=.18,right=.985,bottom=.22,top=.78,wspace=.31)
    fig.suptitle("What graph structure and token cost add to memory retrieval",x=.025,y=.98,ha="left",weight="bold",fontsize=15)
    cols=["#205965","#a55233"]
    for ax in (a,b):
        ax.spines[["right","top"]].set_visible(False);ax.set_axisbelow(True)
    a.grid(axis="x",color="#d6dfdc");a.set_xlim(0,9.65);a.set_xticks([0,2,4,6,8])
    for j,(key,label) in enumerate([("cost-dense","Full model vs. dense"),("role-global","Relative degree added"),("cost-role","Token cost added")]):
        v=d[key+".FS2048"];y=2-j;lo,hi=v["crossed_ci95"];x=v["pp"]
        a.errorbar(x,y,xerr=[[x-lo],[hi-x]],fmt="o",color=cols[0],capsize=3,ms=6)
        a.text(x,y+.22,f"+{x:.2f}",ha="center",fontsize=9,color=cols[0])
    a.set(ylim=(-.48,2.53),yticks=[2,1,0],yticklabels=["Full model vs. dense","Relative degree added","Token cost added"],xlabel="Full Support gain at 2,048 tokens (pp)")
    a.set_title("A   Paired graph ablations",loc="left",fontsize=11,weight="bold",pad=9)
    b.axhline(0,lw=.9,color="#555d5d");b.grid(axis="y",color="#d6dfdc")
    for metric,label,hue,pos,marker in [("FS","Full Support",cols[0],-.065,"o"),("C","Character coverage",cols[1],.065,"s")]:
        v=[d["cost-role."+metric+str(k)] for k in budgets];x=np.arange(6)+pos;pred=np.array([r["pp"] for r in v]);ci=np.array([r["crossed_simultaneous_ci95"] for r in v])
        b.errorbar(x,pred,yerr=[pred-ci[:,0],ci[:,1]-pred],fmt=marker,ls="none",c=hue,ms=5,capsize=2.6,label=label)
    b.set(xticks=range(6),xticklabels=["256","512","1k","2k","4k","8k"],xlabel="Context budget (tokens)",ylabel="Cost-trained minus fixed graph (pp)",ylim=(-1.5,3))
    b.set_title("B   Effect across reading budgets",loc="left",fontsize=11,weight="bold",pad=9)
    b.legend(loc="upper right",frameon=False,fontsize=8,handletextpad=.3)
    fig.text(.025,.035,"ISETrace · 2,000 questions, 1,207 trajectories, five encoder seeds. 95% crossed-bootstrap intervals; panel B adjusts across six budgets per metric.",fontsize=8,color="#3d484b")
    fig.savefig(HERE/"budget-effects.png",dpi=190)
    fig.savefig(HERE/"budget-effects.pdf",metadata={"Creator":"Matplotlib","CreationDate":None,"ModDate":None})
if __name__=="__main__":main()

"""Plot end-of-stream storage and realized BM25 read, reported as query-level percentages."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

D=Path(__file__).resolve().parent
test=json.loads((D/"write_learned/results.json").read_bytes())["modes"]["tokens"]["all"]
dev=json.loads((D/"write_learned/transfer-results.json").read_bytes())["dev"]
order=["fifo","output_head","positional","full"]
labels=["Последние фрагменты (FIFO)","Начала с приоритетом результата","Модель с позицией и ролью","Модель с текстом и инструментом"]
fig,axes=plt.subplots(1,2,figsize=(11.2,4.5),sharex=True,sharey=True)
fig.subplots_adjust(left=.285,right=.975,bottom=.17,top=.76,wspace=.14)
for ax,(n,vals,title) in zip(axes,[(test["n"],test["arms"],"Test"),(dev["q"],dev["arms"],"Dev")]):
    ax.set_title(f"{title}   ·   {n:,} вопросов".replace(","," "),loc="left",fontsize=12,pad=12)
    for j,k in enumerate(order):
        a=vals[k] if title=="Test" else vals["tokens/"+k]
        r,w=[100*a[key]/n for key in (("read_count","write_count") if title=="Test" else ("read","write"))]
        y=len(order)-1-j
        ax.plot([r,w],[y,y],c="#aabcc4",lw=2.6,zorder=1)
        for v,color,off,ha in [(r,"#0b526e",-5,"right"),(w,"#bf581b",5,"left")]:
            ax.scatter([v],[y],c=color,s=47,zorder=2)
            ax.annotate(f"{v:.1f}".replace(".",","),(v,y),xytext=(off,5),textcoords="offset points",ha=ha,color=color,fontsize=8.5)
    ax.set_xlim(20,89);ax.set_ylim(-.6,3.6);ax.set_xticks([20,40,60,80])
    ax.grid(axis="x",color="#dce1e4",lw=.75);ax.set_axisbelow(True)
    ax.tick_params(axis="both",length=0,pad=6,labelsize=10)
    for spine in ax.spines.values():spine.set_visible(False)
axes[0].set_yticks(range(4),labels[::-1])
fig.text(.025,.93,"Где теряется полный комплект свидетельств",fontsize=17,weight="bold",ha="left")
fig.text(.026,.853,"ISETrace  •  Запись 8 192 токена, выдача BM25 2 048 токенов",fontsize=11,ha="left",color="#46565f")
handles=[Line2D([],[],marker="o",color=c,ls="",label=l) for c,l in [("#0b526e","Выдано читателю"),("#bf581b","Сохранено в памяти")]]
fig.legend(handles=handles,loc="lower left",frameon=False,ncol=2,bbox_to_anchor=(.014,.01))
fig.text(.976,.06,"Доля вопросов с полным комплектом, %",ha="right",fontsize=10,color="#46565f")
fig.savefig(D/"write-read.png",dpi=175,facecolor="white")


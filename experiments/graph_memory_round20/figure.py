"""Plot the effect of query-conditioned graph features and degree-preserving re-wiring."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
D=Path(__file__).resolve().parent
data=json.loads((D/"typed_reader/results.json").read_bytes())["means"]
order=[("dense","Исходный Dense-FT"),("rank_only","Только признаки ранга"),("untyped","Соседи без типов"),("typed","Настоящие типизированные связи"),("typed_on_shuffled","Те же веса, соседи перемешаны"),("shuffled","Обучение и тест со сдвигом связей")]
xvals=lambda f:[100*data[k+"/"+f]["full_support"] for k,_ in order]
fig,ax=plt.subplots(figsize=(9,4.3),layout="constrained")
y=list(range(len(order)));pref=xvals("prefix");skip=xvals("skip")
ax.hlines(y,pref,skip,lw=2.1,color="#b7c4ca")
ax.scatter(pref,y,marker="o",s=64,color="#1a5770",zorder=3,label="Префикс")
ax.scatter(skip,y,marker="D",s=48,color="#a5551d",zorder=3,label="Добор целых узлов")
for j,(a,b) in enumerate(zip(pref,skip)):
    ax.annotate(f"{a:.2f}".replace(".",","),(a,j),xytext=(-7,0),textcoords="offset points",ha="right",va="center",fontsize=9,color="#1a465b")
    ax.annotate(f"{b:.2f}".replace(".",","),(b,j),xytext=(7,0),textcoords="offset points",ha="left",va="center",fontsize=9,color="#803c11")
ax.set_yticks(y,[label for _,label in order]);ax.set_ylim(len(order)-.5,-.65);ax.set_xlim(70.5,83)
ax.set_xlabel("Вопросы с полностью извлечённым свидетельством, %")
ax.set_title("ISETrace · 2 000 вопросов · 2 048 WordPiece",loc="left",fontsize=14,pad=12)
ax.grid(axis="x",alpha=.23);ax.spines[["top","right","left"]].set_visible(False);ax.tick_params(axis="y",length=0,pad=8)
ax.legend(loc="upper center",bbox_to_anchor=(.5,-.15),frameon=False,ncol=2,fontsize=9)
fig.savefig(D/"graph-ablation.png",dpi=170,bbox_inches="tight")


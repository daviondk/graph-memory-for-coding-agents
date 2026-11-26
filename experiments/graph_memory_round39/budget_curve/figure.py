"""Render the registered six-budget curves from the signed result table."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import D,BUDGETS,read


def main():
    result=read(D/"results.json")
    x=list(range(len(BUDGETS)))
    colors={"R35/graph_dp":"#084c42","R35/firstfit":"#5b6574","full_rgcn/firstfit":"#c4651a","wo_chunk_adjacency/firstfit":"#7961a6"}
    text={"R35/graph_dp":"R35 + рюкзак","R35/firstfit":"R35 first-fit","full_rgcn/firstfit":"R-GCN first-fit","wo_chunk_adjacency/firstfit":"Без смежности, first-fit"}
    fig,axs=plt.subplots(1,2,figsize=(11,4.25),layout="constrained")
    for name,c in colors.items():
        values=[100*result["means"][name][result["metrics"].index(f"FullSupport@{b}")] for b in BUDGETS]
        axs[0].plot(x,values,color=c,marker="o",markersize=4,linewidth=2 if name=="R35/graph_dp" else 1.4,
                    linestyle="-" if name=="R35/graph_dp" else "--",label=text[name])
    axs[0].set(ylabel="Полное покрытие, %",title="Пакеты при ограничении токенов")
    axs[0].legend(loc="lower right",fontsize=8,frameon=False)
    pair=result["contrasts"]["R35/firstfit"]
    ids=[result["contrast_metrics"].index(f"FullSupport@{b}") for b in BUDGETS]
    y=[100*pair["delta"][j] for j in ids]
    low,high=[[100*v[j] for j in ids] for v in pair["crossed_ci"]]
    axs[1].fill_between(x,low,high,color="#71a49b",alpha=.32,label="95% интервал для R35 first-fit")
    axs[1].plot(x,y,marker="o",color="#084c42",linewidth=2,label="Против R35 first-fit")
    strong=result["contrasts"]["wo_chunk_adjacency/graph_dp"]
    axs[1].plot(x,[100*strong["delta"][j] for j in ids],linestyle="--",marker="s",markersize=4,
                color="#7961a6",label="Против гибрида без смежности")
    axs[1].axhline(0,color="#657480",linewidth=1)
    axs[1].set(ylabel="Разность полного покрытия, п.п.",title="R35 с рюкзаком относительно контролей")
    axs[1].legend(loc="best",fontsize=8,frameon=False)
    for ax in axs:
        ax.set_xticks(x,[str(b) for b in BUDGETS])
        ax.set_xlabel("Бюджет, токены · шаг log₂")
        ax.grid(axis="y",color="#d7dfdf",linewidth=.6)
        ax.spines[["top","right"]].set_visible(False)
        ax.tick_params(labelsize=9)
    fig.savefig(D/"budget-curves.png",dpi=180)
    plt.close(fig)


if __name__=="__main__":
    main()

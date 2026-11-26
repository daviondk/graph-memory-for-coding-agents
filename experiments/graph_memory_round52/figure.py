"""Plot per-endpoint paired effects from the stored estimates."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt

D=Path(__file__).resolve().parent
def source(name):return json.loads((D/name/"results.json").read_bytes())
def display(r):
    if "delta_pp" in r:return [r["delta_pp"],*r["ci95_pp"]]
    return [100*x for x in [r["delta"],*r["ci95"]]]

def main():
    direct=source("global_policy")["contrast"]["primary_href vs primary_text"]
    first=source("global_confirm")["train_confirm"]["contrasts"]["primary_href vs primary_text"]
    large=source("global_confirm/large")["independent_12000"]["contrasts"]["primary_href vs primary_text"]
    hotpot=source("global_hotpot")["contrasts"]["primary_href-primary_text"]["full"]
    dev=source("global_answers")["comparisons"]["primary_text"]["f1"]
    conf=source("global_answers/confirm")["comparisons"]["primary_href vs primary_text"]["f1"]
    supp=source("global_answers/confirm/supplement")["fallback"]["paired"]["f1"]
    series=[
      ("Полное покрытие опор из каталога",["2Wiki dev · 12 576","2Wiki, новые адреса · 2 400","2Wiki, повторная проверка · 12 000","HotpotQA, тот же каталог · 1 280"],[direct,first,large,hotpot]),
      ("Answer F1, Qwen3-4B",["2Wiki dev · 384","Новые адреса · 512","Те же 512, обучаемое правило¹"],[dev,conf,supp])]
    fig,axes=plt.subplots(1,2,figsize=(12.5,3.7),layout="constrained")
    for ax,(title,labels,data) in zip(axes,series):
        ax.axvline(0,color="#7e8886",lw=.8);ax.grid(axis="x",color="#dce5df",lw=.7)
        ax.set_axisbelow(True)
        for i,raw in enumerate(data):
            center,lo,hi=display(raw);y=len(data)-1-i
            ax.errorbar(center,y,xerr=[[center-lo],[hi-center]],fmt="o",color="#175e50",capsize=3,lw=1.7)
            ax.annotate(f"+{center:.2f}".replace(".",","),(center,y),xytext=(0,10),textcoords="offset points",fontsize=9,ha="center")
        ax.set(yticks=list(range(len(data)-1,-1,-1)),yticklabels=labels,ylim=(-.5,len(data)-.45),
               xlabel="Разность, п.п. (парный 95% ДИ)")
        ax.set_title(title,loc="left",fontsize=12);ax.spines[["top","right","left"]].set_visible(False);ax.tick_params(axis="y",length=0)
    axes[0].set_xlim(-.4,12);axes[1].set_xlim(-.2,4.8)
    fig.suptitle("Что даёт переход по проверенной ссылке вместо буквального совпадения",fontsize=15,ha="left",x=.01)
    fig.supxlabel("¹ Дополнительное парное сравнение. Для каждого вопроса двум условиям выделена одна и та же длина контекста.",fontsize=8,x=.01,ha="left")
    fig.savefig(D/"graph-read-effects.pdf",metadata={"CreationDate":None,"ModDate":None})
    plt.close(fig)
if __name__=="__main__":main()


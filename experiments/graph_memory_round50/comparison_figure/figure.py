"""Render selected paired effect sizes from the archived numerical reports."""
from pathlib import Path
import hashlib,json,os
D=Path(__file__).resolve().parent
def read(study,name="results.json"):
    source=D.parent/study;data=(source/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==json.loads((source/"manifest.json").read_bytes())["files"][name]
    return json.loads(data)
def rows():
    pairs=read("matched_reader")["checkpoints"]["recall"]["comparisons"]
    def matched(right):
        r=next(v for v in pairs if v["left"]=="guarded_dp" and v["right"]==right)
        return [100*x for x in (r["quality_delta"][0],*r["quality_ci"][0])]
    def qa(study,c):
        r=read(study)["groups"]["all"]["contrasts"][c]
        return [r["pp"][1],*r["cluster_ci"][1]]
    def cache(study):
        p=read(study)
        r=p["panels"]["R49"]["arms"]["proposed"] if study=="cache_prediction" else p["stats"]["frequency_cost"]
        return [100*x for x in (r["delta"],*r["ci"])]
    return [
        ["ISETrace · Полное покрытие при 2 048 токенах",[
        ["Точная упаковка против нативного first-fit",matched("firstfit")],
        ["Точная упаковка против жадной по полезности",matched("value")],
        ["Голосование против жадной по средней полезности",read("packet_consensus")["recall"]["contrasts"]["votes_greedy"]["mean_greedy"]]]],
        ["2WikiMultiHopQA · Качество ответа Qwen, F1",[
        ["Упоминание против лексического поиска · dev",qa("qa_external","true-lex")],
        ["Упоминание против лексического поиска · репликация",qa("qa_replication","true-lex")],
        ["Обязательное упоминание против плотного поиска",qa("semantic_address","linked_dense-dense")],
        ["Порог против плотного поиска · новые 640",qa("adaptive_address","adaptive-dense")],
        ["Тот же порог · подтверждение на 1 280",qa("gate_confirmation","adaptive-dense")]]],
        ["SERBench · Сэкономленные входные токены",[
        ["Графовая политика против частоты × цены · Cal500",cache("cache_prediction")],
        ["Графовая политика против частоты × цены · Test500",cache("cache_replication")]]]]
def render():
    os.environ.setdefault("MPLCONFIGDIR",str(Path(os.environ.get("TEMP",str(D)))/"r50-mpl"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    table=rows()
    fig=plt.figure(figsize=(11.6,8.0),facecolor="white")
    fig.text(.035,.95,"Графовая память в парных сравнениях",fontsize=21,weight="bold",color="#1b342d")
    fig.text(.035,.91,"Разность метрики, процентные пункты. Интервалы 95%. У каждой панели своя шкала.",fontsize=11,color="#40554c")
    box=fig.add_gridspec(3,1,left=.45,right=.75,top=.82,bottom=.08,hspace=.85,height_ratios=[3,5,2])
    for j,(title,data) in enumerate(table):
        ax=fig.add_subplot(box[j]);ax.set_ylim(-.65,len(data)-.35)
        ax.axvline(0,color="#77847d",lw=1,ls="--")
        ax.set_yticks([])
        for side in ("top","left","right"):ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#ccd2ce")
        ax.tick_params(axis="x",labelsize=9,length=3,color="#a2aea6")
        b=ax.get_position()
        fig.text(.035,b.y1+.023,title,fontsize=13,weight="bold",color="#182e26")
        for i,(label,(v,lo,hi)) in enumerate(data):
            y=len(data)-i-1
            fy=b.y0+(y+.65)/(len(data)+.30)*b.height
            fig.text(.035,fy,label,ha="left",va="center",fontsize=9.8)
            color="#1b6650" if lo>0 or hi<0 else "#607179"
            ax.errorbar([v],[y],xerr=[[v-lo],[hi-v]],fmt="o",ms=5,color=color,lw=1.8,capsize=3)
            stat=(f"{v:+.2f}  [{lo:+.2f}, {hi:+.2f}]").replace(".",",").replace(", +","; +").replace(", -","; −")
            fig.text(.79,fy,stat,fontsize=10,color=color,ha="left",va="center")
        ax.margins(x=.12)
    fig.savefig(D/"comparisons.png",dpi=150)
    fig.savefig(D/"comparisons.pdf",metadata={"CreationDate":None,"ModDate":None})
    plt.close(fig)
if __name__=="__main__":
    (D/"effects.json").write_text(json.dumps(rows(),ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    render()


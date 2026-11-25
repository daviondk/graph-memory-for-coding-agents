"""Apply two frozen packing policies to a sealed full no-next R-GCN ranking."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean
from unittest.mock import patch
import hashlib
import shutil
import sys

D=Path(__file__).resolve().parent
WORK=D.parents[1]
R20=WORK/"graph_memory_round20"
BASE=R20/"residual_graph/adjacency_control/full"
sys.path.insert(0,str(R20))
sys.path.insert(0,str(R20/"fine_train"))
import apply as learned
import render_audit as render
from assess import save,load,pilot,compare,independent,OFF
ARMS=("skip","ratio")
TAG="no-next"

def source(i):return BASE/f"forecasts-rgcn-{i}.json.gz"
def lock():
    plan=load(D/"plan.json")
    assert plan["before_forecast"] and plan["rank_files_present"]==0
    assert pilot.sha(D/"PROTOCOL_RU.md")==plan["protocol"]
    for name,h in plan["parents"].items():assert pilot.sha(R20/name)==h
    up=load(BASE/"forecast-seal.json")
    for i in range(8):assert up["forecasts"][source(i).name]==pilot.sha(source(i))
    mod=D/"model.json"
    if not mod.exists():shutil.copyfile(R20/"fine_train/model.json",mod)
    assert pilot.sha(mod)==plan["parents"]["fine_train/model.json"]

def decide(i):
    original=learned.rd.choose
    def two(*args):
        arms=original(*args)
        return {a:arms[a] for a in ARMS}
    with patch.object(learned,"rank_file",lambda stage,idx:source(idx)), patch.object(learned.rd,"choose",two):
        return learned.predict_shard((TAG,i,D))

def actual(i):
    with patch.object(render,"ARMS",ARMS):return render.shard((str(D),TAG,i))

def predict():
    lock()
    with ProcessPoolExecutor(2) as ex: stamps=list(ex.map(decide,range(8)))
    save(D/f"{TAG}-forecast-seal.json",{"plan":pilot.sha(D/"plan.json"),"model":pilot.sha(D/"model.json"),"upstream":pilot.sha(BASE/"forecast-seal.json"),
        "code":pilot.sha(Path(__file__)),"files":{f"{TAG}-decisions-{i}.json.gz":h for i,h in enumerate(stamps)}})
    with ProcessPoolExecutor(2) as ex: stamps=list(ex.map(actual,range(8)))
    save(D/f"{TAG}-render-seal.json",{"forecast":pilot.sha(D/f"{TAG}-forecast-seal.json"),"files":{f"{TAG}-render-{i}.json.gz":h for i,h in enumerate(stamps)},
        "tokenizer":pilot.sha(Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")),"renderer":pilot.sha(R20/"render_audit.py")})

def score():
    rd=load(D/f"{TAG}-render-seal.json");pred=load(D/f"{TAG}-forecast-seal.json")
    assert rd["forecast"]==pilot.sha(D/f"{TAG}-forecast-seal.json") and pred["code"]==pilot.sha(Path(__file__))
    gold=load(OFF/"gold-spans.json.gz");cohort={x["query_id"]:x["trajectory_id"] for x in load(OFF/"cohort.json")}
    assert set(gold)==set(cohort) and len(gold)==2000 and len(set(cohort.values()))==1207
    rows={a:{} for a in ARMS}
    for i in range(8):
        dp=D/f"{TAG}-decisions-{i}.json.gz";rp=D/f"{TAG}-render-{i}.json.gz"
        assert pilot.sha(dp)==pred["files"][dp.name] and pilot.sha(rp)==rd["files"][rp.name]
        decisions=load(dp);qas={q:(r,a) for r in decisions for q,a in r["picks"].items()}
        for row in load(rp):
            q=row["q"];t=row["t"];ad=row["addr"];record,arms=qas.pop(q)
            assert t==cohort[q]==record["t"] and record["addresses"]==ad and set(arms)==set(ARMS)
            truth=tuple(pilot.SourceSpan.model_validate(s) for s in gold[q])
            for a in ARMS:
                nominal,real,paid,parts=row["picks"][a]
                assert q not in rows[a] and max(paid,nominal)<=2048
                nodes=[]
                for k in arms[a]:
                    e,l,h,c=record["used"][k];eid,ptr=ad[e]
                    sp=pilot.SourceSpan(event_id=eid,json_pointer=ptr,char_start=l,char_end=h)
                    nodes.append(pilot.RankedNodeRecord(node_id=k,score=0,token_count=c,source_spans=(sp,)))
                assert sum(x.token_count for x in nodes)==nominal
                nat=pilot.span_metrics_under_token_budget(tuple(nodes),truth,2048)
                cc,dd,ff=independent(gold[q],[v.model_dump() for v in nodes])
                assert abs(cc-nat.coverage)<1e-12 and abs(dd-nat.density)<1e-12 and ff==nat.full_support
                spans=[{"event_id":ad[e][0],"json_pointer":ad[e][1],"char_start":l,"char_end":h} for e,l,h in parts]
                c,d,f=independent(gold[q],[{"source_spans":[sp]} for sp in spans])
                assert c<=cc+1e-12 and f<=ff
                if real<=2048:assert abs(c-cc)<1e-12 and paid==real
                rows[a][q]={"t":t,"full_support":f,"coverage":c,"density":d,"f1":2*c*d/(c+d) if c+d else 0.,"tokens":paid,
                    "raw":real,"nominal":nominal,"before_fs":ff,"before_coverage":cc}
        assert not qas
    assert all(set(cells)==set(gold) for cells in rows.values())
    summaries={}
    for a,cells in rows.items():
        v=list(cells.values())
        summaries[a]={k:mean(q[k] for q in v) for k in ("full_support","coverage","density","f1","tokens","nominal")}
        summaries[a].update(hits=sum(q["full_support"] for q in v),trims=sum(q["raw"]>2048 for q in v),lost_hits=sum(q["before_fs"]-q["full_support"] for q in v),
            max_actual=max(q["tokens"] for q in v),max_raw=max(q["raw"] for q in v))
    path=D/"strict-metrics.json.gz";save(path,rows)
    a,b=rows["ratio"],rows["skip"]
    result={"n":len(gold),"clusters":len(set(cohort.values())),"summary":summaries,"pairs":compare(a,b),
            "wins":sum(a[q]["full_support"]>b[q]["full_support"] for q in gold),"losses":sum(a[q]["full_support"]<b[q]["full_support"] for q in gold),
            "source":pilot.sha(BASE/"forecast-seal.json"),"strict_outcomes":pilot.sha(path),"render_seal":pilot.sha(D/f"{TAG}-render-seal.json"),
            "plan":pilot.sha(D/"plan.json"),"code":pilot.sha(Path(__file__))}
    save(D/"results.json",result)
    f=lambda x:f"{100*x:.2f}".replace(".",",")
    out=["# Чтение после полного R-GCN без content.next","На одном и том же ранжировании проверены два замороженных правила выдачи памяти. Оценены фактически отрендеренные интервалы на 2 000 вопросах из 1 207 траекторий.",
         "| Политика | Полный источник | FS, % | Coverage, % | Density, % | F1, % | Токены в среднем | Обрезаний | Потеря FS при обрезании |","|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for a,label in (("skip","Целые PU по рангу, пропуск длинных"),("ratio","Два PU, затем короткие интервалы по p/c")):
        v=summaries[a];out.append(f"| {label} | {int(v['hits'])} / 2 000 | {f(v['full_support'])} | {f(v['coverage'])} | {f(v['density'])} | {f(v['f1'])} | {v['tokens']:.1f} | {v['trims']} | {int(v['lost_hits'])} |")
    out.extend(["","Попарная разность после и до смены правила на одном и том же вопросе. Интервалы в п.п. получены кластерным bootstrap по траекториям.",""])
    for k in ("full_support","coverage","density","f1"):
        dif=result["pairs"]["differences"][k];l,h=dif["cluster_ci95"];out.append(f"- {k}: {f(dif['estimate'])} [{f(l)}; {f(h)}].")
    out.extend(["",f"Полный источник появился в {result['wins']} ответах и перестал полностью помещаться в {result['losses']}. Фактический максимум для обеих политик — 2 048 токенов.",
                "","Это проверка переноса правила с Dense и полного обычного R-GCN на независимо переобученный вариант без рёбер соседства. Тестовые вопросы совпадают с прежними, выбран один seed и локальный dev500. Многосидовое сравнение и метрика ответов агента требуют дополнительных прогонов.",
                "","[Протокол](PROTOCOL_RU.md) · [План до готовности прогнозов](plan.json) · [Все парные показатели](results.json) · [Индивидуальные оценки](strict-metrics.json.gz)"])
    (D/"REPORT_RU.md").write_text("\n".join(out)+"\n",encoding="utf8")

if __name__=="__main__":
    {"predict":predict,"score":score}[sys.argv[1]]()


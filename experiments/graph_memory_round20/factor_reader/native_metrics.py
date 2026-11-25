"""Compute every Table 2 metric from immutable native-pool rank permutations."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys

from factor import D, ROOT, app, np, load, save, sha
sys.path.insert(0,str(app.OLD/"tail_read"))
from tail import pilot, OFF
from graph_memory.evaluation.span_metrics import span_metrics_at, span_mrr
from graph_memory.evaluation.span_suite import CONTEXT_TOKEN_BUDGETS, normalized_budget_auc

METRICS = ("coverage_512","coverage_1024","coverage_2048","full_support_2048","recall_5","mrr","coverage_auc","full_support_auc")


def points(rr,gold):
    curve = {b:pilot.span_metrics_under_token_budget(rr,gold,b) for b in CONTEXT_TOKEN_BUDGETS}
    return {"coverage_512":curve[512].coverage, "coverage_1024":curve[1024].coverage, "coverage_2048":curve[2048].coverage,
            "full_support_2048":curve[2048].full_support, "recall_5":span_metrics_at(rr,gold,5).coverage,
            "mrr":span_mrr(rr,gold), "coverage_auc":normalized_budget_auc({b:v.coverage for b,v in curve.items()}),
            "full_support_auc":normalized_budget_auc({b:v.full_support for b,v in curve.items()})}


def shard(job):
    stage,i=job
    if stage=="extra80":
        path=ROOT/"untuned_holdout/dense-ranks-extra80.json.gz"
        forecast=D/"hash64-extra-ranks.json.gz"; seal=load(D/"hash64-extra-seal.json")
        assert sha(forecast)==seal["file"] and sha(path)==seal["upstream"]
        gold=load(app.OLD/"write_transfer/gold-spans.json.gz")
    else:
        path=app.rd.source("dense",i)
        forecast=D/f"hash64-ranks-{i}.json.gz"
        seal=load(D/"hash64-seal.json"); assert sha(forecast)==seal["files"][forecast.name]
        gold=load(OFF/"gold-spans.json.gz")
    parents={r["q"]:r for r in load(path)}
    rankings=load(forecast)
    native=None
    if stage in ("hash64","full"):
        graph_root=app.G/("cpu_fallback/hash64" if stage=="hash64" else "")
        fpath=graph_root/f"forecasts-rgcn-{i}.json.gz"
        assert (graph_root/"forecast-seal.json").exists()
        seal_text=(graph_root/"forecast-seal.json").read_text(encoding="utf8")
        assert sha(fpath) in seal_text
        native={r["q"]:r for r in load(fpath)}
    result={}
    for r in rankings:
        q=r["q"]
        original=parents[q];assert r["t"]==original["t"]
        nodes=[pilot.RankedNodeRecord.model_validate(v) for v in original["rr"]]
        truth=tuple(pilot.SourceSpan.model_validate(v) for v in gold[q])
        arms={}
        order=r["orders" if stage=="extra80" else "ranks"]
        if native is None:
            for n in ("dense","degree","factor"):
                arms[n]=tuple(nodes[j] for j in order[n])
        else:
            unit={v.node_id:v for v in nodes};rr=[x["node_id"] for x in native[q]["rr"]]
            assert len(rr)==len(unit)==len(set(rr)) and set(rr)==set(unit)
            arms["rgcn"]=tuple(unit[k] for k in rr)
        for n,rr in arms.items():
            result.setdefault(n,{})[q]={"t":r["t"],**points(rr,truth)}
    return result


def compare(rows,base):
    groups=defaultdict(list)
    for q in sorted(rows):
        assert rows[q]["t"]==base[q]["t"]
        groups[rows[q]["t"]].append([rows[q][m]-base[q][m] for m in METRICS])
    groups=[groups[t] for t in sorted(groups)]
    sizes=np.array([len(v) for v in groups]);sums=np.array([np.sum(v,axis=0) for v in groups])
    rng=np.random.default_rng(13);boot=[]
    for _ in range(40):
        ix=rng.integers(len(groups),size=(250,len(groups)))
        boot.append(sums[ix].sum(axis=1)/sizes[ix].sum(axis=1)[:,None])
    ci=np.quantile(np.concatenate(boot),[.025,.975],axis=0);d=sums.sum(axis=0)/sizes.sum()
    return {m:[float(d[k]),*ci[:,k].tolist()] for k,m in enumerate(METRICS)}


def run(stage):
    assert stage in ("test","extra80","hash64","full")
    with ProcessPoolExecutor(2) as ex:
        shards=list(ex.map(shard,[(stage,i) for i in range(1 if stage=="extra80" else 8)]))
    rows=defaultdict(dict)
    for sh in shards:
        for n,data in sh.items():
            assert not rows[n].keys() & data.keys()
            rows[n].update(data)
    if stage in ("test","extra80"):
        frozen=load(D/(("hash64-extra" if stage=="extra80" else "hash64")+"-outcomes.json.gz"))
        for n,rs in rows.items():
            own=frozen["prefix/"+n]
            assert set(rs)==set(own)
            assert all(rs[q]["coverage_2048"]==own[q]["coverage"] and rs[q]["full_support_2048"]==own[q]["full_support"] for q in rs)
        if stage=="test":
            ref=load(app.OLD/"trained_rank/table1-rows.json.gz")
            assert all(abs(rows["dense"][r["q"]][k]-r[k])<1e-12 for r in ref for k in METRICS[:6])
        comps={n+"-dense":compare(v,rows["dense"]) for n,v in rows.items() if n!="dense"}
    else:
        baseline=load(D/"metrics-test-rows.json.gz")
        assert set(baseline["dense"])==set(rows["rgcn"])
        comps={n+"-rgcn":compare(baseline[n],rows["rgcn"]) for n in ("degree","factor","dense")}
    means={n:{m:float(np.mean([r[m] for r in rs.values()])) for m in METRICS} for n,rs in rows.items()}
    save(D/f"metrics-{stage}-rows.json.gz",rows)
    save(D/f"metrics-{stage}.json",{"rows":sha(D/f"metrics-{stage}-rows.json.gz"),"summary":means,"pairs":comps,"n":len(next(iter(rows.values()))),
         "protocol":sha(D/"NATIVE_METRICS_RU.md"),"code":sha(Path(__file__))})


def fmt(v):
    return f"{v*100:.2f}".replace(".",",")


def report():
    text=["# Дополнительные нативные метрики ISETrace",
          "Каждая строка использует нативные процедуры оценки интервалов из таблицы 2 и нормированную трапецеидальную площадь по шести бюджетам. Повторно посчитаны все доступные вопросы. Проверка по каждой строке исходного Dense-FT воспроизводит шесть метрик сохранённого эталона. Указанные числа выражены в процентах."]
    for stage,title in (("test","Основные 2 000 test"),("extra80","Дополнительные 80 вопросов"),("hash64","R-GCN, 64 тренировочные траектории"),("full","R-GCN, полный train")):
        p=D/f"metrics-{stage}.json"
        if not p.exists():continue
        d=load(p);r=d["summary"]
        tab=["| Вариант | C@512 | C@1024 | C@2048 | FS@2048 | Recall@5 | MRR | Coverage AUC | FS AUC |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for n,row in r.items():
            tab.append("| "+n+" | "+" | ".join(fmt(row[m]) for m in METRICS)+" |")
        text.extend(["## "+title,"\n".join(tab)])
        for name,v in d["pairs"].items():
            text.append(name+" (Δ в п.п., 95% ДИ по траекториям) — "+" · ".join(f"{m} {fmt(v[m][0])} [{fmt(v[m][1])} … {fmt(v[m][2])}]" for m in ("coverage_512","full_support_2048","recall_5","mrr")))
        text.append(f"[Полные парные оценки]({p.name})")
    text.append("В R-GCN hash64 обучается нейросетевой остаток на 101 вопросе. Структурный компонент нашего метода использовал исходный train. Базовый E5 у этих вариантов один. Отдельные результаты основного прогона по одному seed и среднее пяти seed из статьи имеют разный дизайн. [Протокол](NATIVE_METRICS_RU.md) · [ISETrace, табл. 2](https://arxiv.org/html/2609.25913v3#S7.T2)")
    (D/"METRICS_RU.md").write_text("\n\n".join(text)+"\n",encoding="utf8")


if __name__=="__main__":
    for stage in sys.argv[1:]:
        run(stage)
    report()


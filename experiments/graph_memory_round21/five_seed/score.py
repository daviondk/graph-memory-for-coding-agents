"""Source-only fixed-factor forecasts and matched-seed native metrics."""
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from statistics import mean, stdev
import gzip
import hashlib
from pathlib import Path

from study import HERE,WORK,R18,R19,R20,SEEDS,PRIVATE,seed_dir,private,db_ro,load,save,sha,base,f,pilot,np,CACHE,reqs
sys.path.insert(0,str(R20/"factor_reader"))
from native_metrics import METRICS, points

def partial_forecasts(seed,i):
    out=seed_dir(seed)
    old={r["q"]:r for r in load(R19/f"forecasts-main-{i}.json.gz")}
    graph=f.gmod.graph_index()
    p=load(R20/"factor_reader/prior.json")["models"]["prior"]
    if seed==13:
        con=db_ro(base.RUN/"trained-vectors.sqlite3");prec="fp32";cal=load(R20/"factor_reader/hash64-weights.json")["rank"]
    else:
        con=db_ro(private(seed)/"vectors.sqlite");prec="ft";cal=load(out/"calibration.json")["rank"]
    ret=f.DenseTaskRetriever(encoder=f.Lookup(con,prec),device="cpu")
    records=[]
    for src in sorted((CACHE/"projection").glob(f"{i}-*.json.gz")):
        raw=load(src);t=raw["t"]
        keys,z=f.shape(raw["pool"],f.gmod.project(t,graph)); prior=f.lin(p,z[:,p["columns"]]); idx={k:j for j,k in enumerate(keys)}
        for req in reqs(raw):
            q=req.task_id;canonical=old.pop(q);assert canonical["t"]==t
            ref={r["node_id"]:j for j,r in enumerate(canonical["rr"])}
            ids=[n.node_id for n in ret.rank(req)]
            assert len(ref)==len(ids)==len(idx) and set(ref)==set(ids)==set(idx)
            dense=np.asarray([ref[n] for n in ids]);zrank=f.lin(cal,f.rank_x(len(ids)))
            score=zrank+prior[[idx[n] for n in ids]]
            fo=dense[np.argsort(-score,kind="stable")]
            records.append({"q":q,"t":t,"dense":dense.tolist(),"factor":fo.tolist()})
    assert not old
    if seed==13:
        historic={r["q"]:r for r in load(R20/f"factor_reader/hash64-ranks-{i}.json.gz")}
        for row in records:
            k=historic.pop(row["q"])
            assert row["dense"]==k["ranks"]["dense"] and row["factor"]==k["ranks"]["factor"]
        assert not historic
    con.close()
    path=out/f"picks-{i}.json.gz";save(path,records)
    return {"file":path.name,"sha":sha(path),"n":len(records),"source":sha(R19/f"forecasts-main-{i}.json.gz")}


def run_forecast(seed):
    if seed!=13:
        model=load(seed_dir(seed)/"model.json");c=load(seed_dir(seed)/"calibration.json")
        assert c["weights"]==sha(seed_dir(seed)/"model.json") and load(seed_dir(seed)/"embeddings.json")["checkpoint"]==model["files"]["model.safetensors"]
    with ProcessPoolExecutor(2) as ex:
        import itertools
        receipts=list(ex.map(partial_forecasts,itertools.repeat(seed,8),range(8)))
    assert sum(r["n"] for r in receipts)==2000
    save(seed_dir(seed)/"forecast-seal.json",{"seed":seed,"receipts":receipts,"plan":sha(HERE/"plan.json"),"source_prior":sha(R20/"factor_reader/prior.json"),
         "rank_weights":sha(R20/"factor_reader/hash64-weights.json" if seed==13 else seed_dir(seed)/"calibration.json"),"code":sha(Path(__file__))})


def score(seed):
    out=seed_dir(seed);seal=load(out/"forecast-seal.json")
    assert seal["plan"]==sha(HERE/"plan.json") and seal["code"]==sha(Path(__file__))
    gold=load(R18/"isetrace_official/gold-spans.json.gz")
    outcomes={"dense":{},"factor":{}}
    for i,receipt in enumerate(seal["receipts"]):
        path=out/receipt["file"];source=R19/f"forecasts-main-{i}.json.gz"
        assert sha(path)==receipt["sha"] and sha(source)==receipt["source"]
        base_rows={r["q"]:r for r in load(source)}
        for row in load(path):
            q=row["q"];base=base_rows[q];assert base["t"]==row["t"]
            ref=[pilot.RankedNodeRecord.model_validate(x) for x in base["rr"]]
            truth=tuple(pilot.SourceSpan.model_validate(x) for x in gold[q])
            for arm in ("dense","factor"):
                assert sorted(row[arm])==list(range(len(ref))) and q not in outcomes[arm]
                ranked=tuple(ref[j] for j in row[arm]);outcomes[arm][q]={"t":row["t"],**points(ranked,truth)}
    expect={q["q"] for q in load(R19/"split.json.gz")["test"]}
    assert all(set(rows)==expect for rows in outcomes.values()) and len(expect)==2000
    if seed==13:
        hist=load(R20/"factor_reader/metrics-test-rows.json.gz")
        assert all(hist[n]==rs for n,rs in outcomes.items())
    p=out/"metrics.json.gz"; save(p,outcomes)
    save(out/"results.json",{"seed":seed,"n":len(expect),"q_sha":sha(p),"seal":sha(out/"forecast-seal.json"),
      "summary":{a:{m:mean(r[m] for r in d.values()) for m in METRICS} for a,d in outcomes.items()}})


def paired_all(seeds,data):
    original=data[seeds[0]]["dense"];ids=sorted(original)
    assert len(ids)==2000
    packed=defaultdict(list)
    for q in ids:
        t=original[q]["t"]
        assert all(data[s][a][q]["t"]==t for s in seeds for a in ("factor","dense"))
        v=np.asarray([[data[s]["factor"][q][m]-data[s]["dense"][q][m] for m in METRICS] for s in seeds])
        packed[t].append(v.mean(axis=0))
    assert len(packed)==1207
    summed=np.asarray([np.sum(packed[t],axis=0) for t in sorted(packed)]);n=np.array([len(packed[t]) for t in sorted(packed)])
    rng=np.random.default_rng(13);dist=[]
    for _ in range(40):
        ix=rng.integers(0,len(n),size=(250,len(n)))
        dist.append(summed[ix].sum(axis=1)/n[ix].sum(axis=1)[:,None])
    limits=np.quantile(np.concatenate(dist),[.025,.975],axis=0)
    delta=summed.sum(axis=0)/n.sum()
    return {m:[float(delta[k]),*limits[:,k].tolist()] for k,m in enumerate(METRICS)}


def aggregate():
    seeds=[s for s in SEEDS if (HERE/f"seed-{s}/results.json").exists()]
    if not seeds:return
    data={};summary={}
    for s in seeds:
        out=seed_dir(s);res=load(out/"results.json")
        assert res["q_sha"]==sha(out/"metrics.json.gz") and res["seal"]==sha(out/"forecast-seal.json")
        data[s]=load(out/"metrics.json.gz");summary[s]=res["summary"]
    effect=paired_all(seeds,data)
    descriptives={arm:{m:{"mean":mean(summary[s][arm][m] for s in seeds),
                           "sd":stdev(summary[s][arm][m] for s in seeds) if len(seeds)>1 else None} for m in METRICS} for arm in ("dense","factor")}
    result={"seeds":seeds,"completed":len(seeds)==len(SEEDS),"n":2000,"trajectories":1207,"results":{str(s):sha(seed_dir(s)/"results.json") for s in seeds},
      "summary":descriptives,"paired":effect}
    save(HERE/("five-seed-results.json" if result["completed"] else f"interim-{len(seeds)}-results.json"),result)
    title="Пять независимых обучений" if result["completed"] else f"Промежуточная проверка по {len(seeds)} из пяти обучений"
    text=["# "+title, "Рассматриваем один заранее зафиксированный факторизованный prior на графе действий, калибруем семантический ранг отдельно внутри каждого исходного train. Структурные веса едины для всех seed. Две политики внутри пары получают один и тот же обученный Dense-FT и те же PU. Для каждого вопроса и seed сохранён полный порядок источников. Траектории и вопросы повторяются между seed, поэтому размер теста составляет 2 000 вопросов.",
          "## Нативные метрики ISETrace","| Вариант | C@512 | C@1024 | C@2048 | FS@2048 | Recall@5 | MRR |\n|---|---:|---:|---:|---:|---:|---:|"]
    def fmt(v):return f"{v*100:.2f}".replace(".",",")
    for arm in ("dense","factor"):
        cells=[]
        for m in METRICS[:6]:
            r=descriptives[arm][m];cells.append(fmt(r["mean"])+( (" ± "+fmt(r["sd"])) if r["sd"] is not None else ""))
        text[-1]+="\n| "+arm+" | "+" | ".join(cells)+" |"
    text.extend(["## Попарное изменение","Расчёт сначала усредняет внутри каждого вопроса разность по готовым seed, затем пересэмплирует траектории. Результат выражен в п.п. с 95% интервалом."])
    for m in METRICS:
        d,l,h=effect[m];text.append(f"- {m} {fmt(d)} [{fmt(l)} … {fmt(h)}]")
    text.extend(["Включённые seed — "+", ".join(map(str,seeds))+". У исторического seed 13 исходные Dense и factor порядки проверены полным повторным CPU-проходом, все метрики сверены по каждому вопросу. До пяти seed результаты остаются промежуточными. Для статистического сравнения с residual R-GCN требуются пять согласованных массивов исходов этой модели. [Протокол](PROTOCOL_RU.md) · [План и входные хеши](plan.json)"])
    (HERE/"REPORT_RU.md").write_text("\n\n".join(text)+"\n",encoding="utf8")


if __name__=="__main__":
    cmd=sys.argv[1]
    if cmd=="aggregate":aggregate()
    else:{"predict":run_forecast,"score":score}[cmd](int(sys.argv[2]))


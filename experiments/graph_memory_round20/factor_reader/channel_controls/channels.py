"""Train and test fixed within-call and cross-action degree priors on the same units."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import factor as f
from factor import np
sys.path.insert(0, str(f.app.OLD/"tail_read"))
from tail import pilot, independent
sys.path.insert(0, str(f.ROOT/"untuned_holdout"))
from validate_transfer import paired, interval
SRC = f.ROOT/"untuned_holdout"
GROUP = {"local":[7,8,9,10], "cross":[11,12,13,14], "feeds":[11,12], "resource":[13,14]}


def fit():
    prior = f.load(f.D/"prior.json")
    shard_files = [f.P/f"prior-{i}.npz" for i in range(8)]
    assert [f.sha(p) for p in shard_files] == [r["file"] for r in prior["inventory"]]
    p = [np.load(s) for s in shard_files]
    x = np.vstack([s["x"] for s in p])
    y = np.concatenate([s["y"] for s in p])
    w = np.concatenate([s["w"] for s in p])
    assert x.shape==(prior["train_rows"],15)
    models={n:{**f.lr(x[:,cols],y,w),"columns":cols} for n,cols in GROUP.items()}
    models["all"] = prior["models"]["degree"]
    f.save(HERE/"weights.json",{"models":models,"protocol":f.sha(HERE/"PROTOCOL_RU.md"),"code":f.sha(Path(__file__)),"prior":f.sha(f.D/"prior.json"),
                                  "training_rows":len(y),"questions":prior["train_questions"],"trajectories":prior["train_trajectories"]})


def source(stage,i):
    if stage=="test":
        return f.app.rd.source("dense",i)
    assert stage=="extra80" and i==0
    return SRC/"dense-ranks-extra80.json.gz"


def process(job):
    stage,i = job
    ix=f.gmod.graph_index()
    if stage=="extra80":
        for t,item in f.load(f.ROOT/"typed_reader/holdout80/source-plan.json")["records"].items():
            if item["native"]:
                assert ix[t][1]==item["sha"]
            else:
                ix[t]=(Path("D:/CodexResearch/x20-typed-reader-private")/f"{t}.json.gz",item["sha"])
    path=source(stage,i)
    if stage=="extra80":
        assert f.sha(path)==f.load(SRC/"forecast-seal.json")["ranks"]
    params=f.load(HERE/"weights.json")["models"]
    calib=f.load(f.D/"hash64-weights.json")["rank"]
    by=defaultdict(list)
    for row in f.load(path):
        by[row["t"]].append(row)
    out=[]
    records={}
    for t,group in by.items():
        ids,channels,_,_,audit=f.gmod.project(t,ix)
        degrees=np.column_stack([np.log1p(np.bincount(end,minlength=len(ids))) for end,_ in channels])
        prior={n:f.lin(model,degrees[:,[j-7 for j in model["columns"]]]) for n,model in params.items()}
        records[t]={"edges":audit["by_type"],"n_pu":len(ids),"q":len(group),"cross_incident":int(np.any(degrees[:,4:]>0,axis=1).sum())}
        for row in group:
            rr=row["rr"]
            order=np.array([ids[r["node_id"]] for r in rr],dtype=int)
            assert len(order)==len(ids)==len(set(order.tolist()))
            rank=f.lin(calib,f.rank_x(len(rr)))
            scores={n:rank+v[order] for n,v in prior.items()}
            scores["dense"]=-np.arange(len(rr))
            scores["rank"]=rank
            selection={}
            for n,s in scores.items():
                seq=np.argsort(-s,kind="stable")
                selection[n]={pol:f.gmod.pack(seq,[r["token_count"] for r in rr],pol=="skip") for pol in ("prefix","skip")}
            out.append({"q":row["q"],"t":t,"selections":selection})
    target=HERE/f"{stage}-picks-{i}.json.gz"
    f.save(target,{"rows":out,"records":records})
    return {"file":target.name,"sha":f.sha(target),"source":f.sha(path),"n":len(out),"clusters":len(by)}


def predict(stage):
    shards=range(8) if stage=="test" else range(1)
    with ProcessPoolExecutor(max_workers=2) as pool:
        receipts=list(pool.map(process,[(stage,i) for i in shards]))
    assert sum(r["n"] for r in receipts)==(2000 if stage=="test" else 80)
    f.save(HERE/f"{stage}-seal.json",{"receipts":receipts,"protocol":f.sha(HERE/"PROTOCOL_RU.md"),"code":f.sha(Path(__file__)),
           "calibration":f.sha(f.D/"hash64-weights.json"),"model":f.sha(HERE/"weights.json")})


def score(stage):
    seal=f.load(HERE/f"{stage}-seal.json")
    assert seal["code"]==f.sha(Path(__file__)) and seal["model"]==f.sha(HERE/"weights.json")
    gold=f.load((f.gmod.OFF if stage=="test" else f.app.OLD/"write_transfer")/"gold-spans.json.gz")
    results=defaultdict(dict)
    stats={}
    for i,receipt in enumerate(seal["receipts"]):
        fp=HERE/receipt["file"]; path=source(stage,i)
        assert f.sha(fp)==receipt["sha"] and f.sha(path)==receipt["source"]
        data=f.load(fp);stats.update(data["records"])
        base={r["q"]:r["rr"] for r in f.load(path)}
        for row in data["rows"]:
            q=row["q"];rr=base[q];truth=tuple(pilot.SourceSpan.model_validate(s) for s in gold[q]);nodes=[pilot.RankedNodeRecord.model_validate(v) for v in rr]
            for name,p in row["selections"].items():
                for pol,indices in p.items():
                    arm=pol+"/"+name
                    assert q not in results[arm] and len(indices)==len(set(indices))
                    kept=[nodes[x] for x in indices];cost=sum(x.token_count for x in kept);assert cost<=2048
                    m=pilot.span_metrics_under_token_budget(tuple(kept),truth,2048)
                    ref=independent(gold[q],[rr[x] for x in indices])
                    assert all(abs(v-getattr(m,k))<1e-12 for v,k in zip(ref,("coverage","density","full_support"),strict=True))
                    results[arm][q]={"t":row["t"],"tokens":cost,**{k:getattr(m,k) for k in ("coverage","density","full_support","f1")}}
    split="hash64" if stage=="test" else "hash64-extra"
    oldpath=f.D/(split+"-outcomes.json.gz")
    assert oldpath.exists(),oldpath
    old=f.load(oldpath)
    for pol in ("prefix","skip"):
        assert results[pol+"/all"]==old[pol+"/degree"] and results[pol+"/dense"]==old[pol+"/dense"]
    comparisons=[("all","local"),("cross","local"),("all","cross"),("all","dense"),("local","dense"),("cross","dense"),("feeds","dense"),("resource","dense"),("rank","dense")]
    allq=set(results["prefix/dense"])
    crossq={q for q in allq if stats[results["prefix/dense"][q]["t"]]["cross_incident"]>0}
    cells={}
    for group,qset in (("all",allq),("cross_present",crossq),("cross_absent",allq-crossq)):
        if qset:
            cells[group]={pol+"/"+a+"-"+b:paired(results[pol+"/"+a],results[pol+"/"+b],qset) for a,b in comparisons for pol in ("prefix","skip")}
    f.save(HERE/f"{stage}-outcomes.json.gz",results)
    f.save(HERE/f"{stage}-results.json",{"n":len(allq),"trajectories":len(stats),"cross_trajectories":sum(s["cross_incident"]>0 for s in stats.values()),
       "cross_queries":len(crossq),"cross_incident_nodes":sum(s["cross_incident"] for s in stats.values()),"nodes":sum(s["n_pu"] for s in stats.values()),
       "edges":[sum(s["edges"][k] for s in stats.values()) for k in range(4)],"paired":cells,"matched_original":f.sha(oldpath)})


def report():
    names={"all-local":"Все степени / локальные", "all-dense":"Все степени / Dense", "local-dense":"Локальные / Dense", "cross-dense":"Между действиями / Dense",
           "cross-local":"Между действиями / локальные", "feeds-dense":"Только feeds / Dense", "resource-dense":"Только resource flow / Dense"}
    text=["# Локальные и межсобытийные связи графа памяти",
          "Первые четыре счётчика описывают соседство чанков и её связь с аргументами и результатом того же вызова. Следующие четыре описывают направление связей между разными действиями. Для каждого семейства коэффициенты заново обучены на одних исходных примерах. Калибровка Dense общая. Первичный контраст отвечает на вопрос, добавляют ли связи между действиями информацию сверх локальной структуры. Мера качества — полное покрытие всех исходных цитат при 2 048 токенах. У восьмистепенного и базового вариантов по каждому вопросу проверено совпадение всех пяти метрик с независимым пайплайном factor_reader."]
    for stage,label in (("test","Основной test"),("extra80","Дополнительные 80 вопросов")):
        p=HERE/f"{stage}-results.json"
        if not p.exists():continue
        d=f.load(p)
        text.extend(["## "+label,f"Из {d['trajectories']} траекторий в {d['cross_trajectories']} есть межсобытийное ребро. К этим траекториям относятся {d['cross_queries']} из {d['n']} вопросов. Хотя бы одно такое ребро инцидентно {d['cross_incident_nodes']} из {d['nodes']} уникальных узлов. Число направленных рёбер в порядке next, argument–return, feeds, resource flow — {', '.join(str(x) for x in d['edges'])}."])
        tab=["| Пара | Успехи | Выигрыши / потери | Δ Full Support, п.п. [95% ДИ] | Δ Coverage, п.п. [95% ДИ] |","|---|---:|---:|---:|---:|"]
        for k,n in names.items():
            row=d["paired"]["all"]["prefix/"+k]
            tab.append(f"| {n} | {row['hits']} / {row['base_hits']} | {row['wins']} / {row['losses']} | {interval(row,'full_support')} | {interval(row,'coverage')} |")
        text.extend(["\n".join(tab),f"[Полные оценки, добор и разделение по наличию ребра]({p.name})"])
    text.append("[Зафиксированный план](PROTOCOL_RU.md) · [Веса](weights.json) · [Реализация](channels.py)")
    (HERE/"REPORT_RU.md").write_text("\n\n".join(text)+"\n",encoding="utf8")


if __name__=="__main__":
    cmd=sys.argv[1]
    if cmd=="fit":fit()
    elif cmd=="report":report()
    else:{"predict":predict,"score":score}[cmd](sys.argv[2])


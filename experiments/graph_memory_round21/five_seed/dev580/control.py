"""Audit the upstream Dense-FT checkpoint selector on both development partitions."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import hashlib
import sys

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parent))
import study as run
from study import base, load, save, sha
from graph_memory.models.dense_finetune import training as native
from graph_memory.models.dense_finetune.contracts import DenseFinetuneTaskLocalEvaluatorPayload
from graph_memory.embeddings import load_sentence_transformer

OFF = run.WORK / "graph_memory_round22/native_multiseed/official580"
GRAPHS = Path("D:/CodexResearch/x20-native-multiseed/official580/dev")
METRICS = ("recall_at_2","recall_at_5","recall_at_10","mrr")
EVAL = native._TaskLocalDenseFinetuneEvaluator
ORIGINAL = EVAL.__call__
PRIV = run.PRIVATE / "dev580"


def out(s):
    p = D / f"seed-{s}"
    p.mkdir(exist_ok=True)
    return p


def plan():
    protocol = D / "PROTOCOL_RU.md"
    split = load(OFF / "split.json.gz")
    assert split["dev"][:500] == load(run.R19 / "split.json.gz")["dev"]
    assert len(split["dev"]) == 580 and len({r["t"] for r in split["dev"]}) == 352
    trained = load(run.R19 / "trained-checkpoint.json")["metrics"]
    refs = (protocol,D/"control.py",OFF/"split-audit.json",OFF/"split.json.gz",run.HERE/"plan.json",Path(native.__file__))
    delta = 500*(trained[1]["dev_recall_at_5"]-trained[0]["dev_recall_at_5"])
    save(D/"plan.json",{"parents":{p.name if p.parent==D else str(p):sha(p) for p in refs},
         "seed_13_prior_margin_in_sum":delta,"extra_worst_case":80,"seeds":run.SEEDS,"selected":"earliest maximum average native PU Recall@5",
         "epoch0_input_weight":sha(base.WEIGHTS/"model.safetensors")})


def payload(n):
    split = load(OFF/"split.json.gz")["dev"]
    if n==500:
        reqs,labs,_=base.pools("dev")
    else:
        assert n==580
        graphs=load(OFF/"dev-graphs.json")
        requests={}; labels={}
        for t,receipt in sorted(graphs.items()):
            p=GRAPHS/(t+".json.gz")
            assert sha(p)==receipt["graph_file"]
            row=load(p)

            from graph_memory.graphs.provenance.contracts import ProvenanceGraph
            pool=base.pilot.native.provenance_unit_candidates(ProvenanceGraph.model_validate(row["g"]))
            for q,text in row["q"]:
                requests[q]=base.pilot.TextRankingRequest(task_id=q,query_text=text,candidates=pool)
                labels[q]=base.EvidenceLabel(task_id=q,gold_answer="",gold_evidence_item_ids=tuple(row["labels"][q]),gold_dependency_edges=())
        reqs=[requests[z["q"]] for z in split];labs=[labels[z["q"]] for z in split]
        assert len(requests)==580
    assert [r.task_id for r in reqs]==[p["q"] for p in split[:n]]
    return DenseFinetuneTaskLocalEvaluatorPayload(requests=tuple(reqs),labels=tuple(labs))


@contextmanager
def capture(sink):
    # Python 3.12 notifies only on return of this evaluator's code object.
    # Native numpy, torch operations and the trainer's return value are untouched.
    mon=sys.monitoring
    slot=next(i for i in (3,4,5,0,1,2) if mon.get_tool(i) is None)
    mon.use_tool_id(slot,"isetrace-development-receipt")
    def callback(code,offset,returned):
        frame=sys._getframe(1)
        assert frame.f_code is ORIGINAL.__code__
        ev=frame.f_locals["self"]
        rows={r.task_id:{k:float(v[k]) for k in METRICS} for r,v in zip(ev.payload.requests,frame.f_locals["metric_rows"],strict=True)}
        assert len(rows)==len(ev.payload.requests)
        assert all(abs(sum(row[k] for row in rows.values())/len(rows)-ev.metric_values["dev_"+k])<1e-13 for k in METRICS)
        sink(rows,dict(ev.metric_values),frame.f_locals["model"])
    mon.register_callback(slot,mon.events.PY_RETURN,callback)
    mon.set_local_events(slot,ORIGINAL.__code__,mon.events.PY_RETURN)
    try:
        yield
    finally:
        mon.set_local_events(slot,ORIGINAL.__code__,0)
        mon.register_callback(slot,mon.events.PY_RETURN,None)
        mon.free_tool_id(slot)


def write_epochs(target,n,epoch,rows,metrics):
    rp=target/f"dev{n}-e{epoch}-rows.json.gz"
    order=hashlib.sha256(("\n".join(rows)+"\n").encode()).hexdigest()
    save(rp,rows)
    save(target/f"dev{n}-e{epoch}.json",{"rows":sha(rp),"n":n,"ordered_q_sha":order,"means":metrics,"protocol":sha(D/"plan.json")})


def fit(s):
    assert s!=13
    o=out(s);history=[]
    def sink(rows,metrics,model):
        ep=len(history);assert ep in (0,1) and len(rows)==500
        write_epochs(o,500,ep,rows,metrics)
        if ep and metrics["dev_recall_at_5"]<=history[0]["dev_recall_at_5"]:
            run.check_space(2*1024**3,"unselected trained checkpoint")
            parent=PRIV/f"seed-{s}";parent.mkdir(parents=True,exist_ok=True)
            i=0
            while (parent/f"extra-epoch1-{i:03d}").exists():i+=1
            cp=parent/f"extra-epoch1-{i:03d}"
            model.save(str(cp))
            save(o/"extra-epoch1.json",{"path":str(cp),"weight":sha(cp/"model.safetensors")})
        history.append(metrics)
    with capture(sink):
        run.fit(s)
    m=load(run.seed_dir(s)/"model.json")
    assert len(history)==2
    for ep,metric in enumerate(history):
        assert all(m["log"][ep]["dev_"+k]==metric["dev_"+k] for k in METRICS)
    save(o/"capture.json",{"model":sha(run.seed_dir(s)/"model.json"),"panels":[sha(o/f"dev500-e{e}.json") for e in (0,1)]})


def paths(s):
    if s==13:
        log=load(run.R19/"trained-checkpoint.json")["metrics"]
        selected=base.RUN/"model"
    else:
        meta=load(run.seed_dir(s)/"model.json")
        log=meta["log"];selected=run.as_path(meta)
    best=int(log[1]["dev_recall_at_5"]>log[0]["dev_recall_at_5"])
    cp1=selected if best else Path(load(out(s)/"extra-epoch1.json")["path"])
    return [base.WEIGHTS,cp1],best,selected,log


def measure(s,n,ep,cp,tasks):
    target=out(s)
    if (target/f"dev{n}-e{ep}.json").exists():return
    model=load_sentence_transformer(str(cp),device="cuda").eval()
    ev=EVAL(payload=tasks,query_prefix=base.SET.query_prefix,passage_prefix=base.SET.passage_prefix,
            batch_size=base.SET.trainer.eval_batch_size,selected_metric="dev_recall_at_5")
    seen=[]
    def sink(rows,metrics,_):
        assert len(rows)==n;write_epochs(target,n,ep,rows,metrics);seen.append(True)
    with capture(sink):
        ev(model)
    assert seen==[True]


def select(s):
    run.pin(s)
    cps,epoch500,selected500,log=paths(s);target=out(s)
    for n in (500,580):
        tasks=None
        for ep,cp in enumerate(cps):
            p=target/f"dev{n}-e{ep}.json"
            if ep==0 and s!=13 and not p.exists():
                first=out(13);info=load(first/p.name)
                assert sha(cp/"model.safetensors")==load(D/"plan.json")["epoch0_input_weight"]
                assert len(load(first/f"dev{n}-e0-rows.json.gz"))==n
                shutil.copyfile(first/f"dev{n}-e0-rows.json.gz",target/f"dev{n}-e0-rows.json.gz")
                assert sha(target/f"dev{n}-e0-rows.json.gz")==info["rows"]
                save(p,{**info,"shared_seed13":sha(first/p.name)})
            if not p.exists():
                if tasks is None:tasks=payload(n)
                measure(s,n,ep,cp,tasks)
        del tasks
    metrics={n:[load(target/f"dev{n}-e{ep}.json")["means"] for ep in (0,1)] for n in (500,580)}
    assert all(abs(metrics[500][ep]["dev_"+k]-log[ep]["dev_"+k])<1e-12 for k in METRICS for ep in (0,1))
    ep580=int(metrics[580][1]["dev_recall_at_5"]>metrics[580][0]["dev_recall_at_5"])
    cp580=selected500 if ep580==epoch500 else cps[ep580]
    names=[f"dev{n}-e{ep}-rows.json.gz" for n in (500,580) for ep in (0,1)]
    assert all(sha(target/name)==load(target/name.replace("-rows.json.gz",".json"))["rows"] for name in names)
    weight500=sha(selected500/"model.safetensors");weight580=sha(cp580/"model.safetensors")
    save(target/"selection.json",{"seed":s,"epoch_500":epoch500,"epoch_580":ep580,
        "weight_500":weight500,"weight_580":weight580,"path_500":str(selected500),"path_580":str(cp580),
        "same_choice":epoch500==ep580,"weight_by_epoch":[sha(cp/"model.safetensors") for cp in cps],
        "per_query":{name:sha(target/name) for name in names},"metrics":metrics,
        "margin_sum500":500*(metrics[500][1]["dev_recall_at_5"]-metrics[500][0]["dev_recall_at_5"]),
        "split":sha(OFF/"split.json.gz"),"plans":[sha(D/"plan.json"),sha(run.HERE/"plan.json")]})
    print("selection",s,epoch500,ep580,weight580,flush=True)
    report()


def report():
    lines=["# Контроль выбора Dense-FT на полном dev","Числа в таблице — средний нативный Recall@5 по идентификаторам PU в процентах. Эпоха 0 соответствует исходному E5.","| Seed | Dev500, эпоха 0 | Dev500, эпоха 1 | Dev580, эпоха 0 | Dev580, эпоха 1 | Выбор 500 / 580 |","|---:|---:|---:|---:|---:|---:|"]
    for s in run.SEEDS:
        p=D/f"seed-{s}/selection.json"
        if p.exists():
            r=load(p);scores=[r["metrics"][str(n)][ep]["dev_recall_at_5"]*100 for n in (500,580) for ep in (0,1)]
            lines.append("| "+str(s)+" | "+" | ".join(f"{v:.3f}" for v in scores)+f" | {r['epoch_500']} / {r['epoch_580']} |")
    lines.extend(["","Для каждой завершённой строки каталог seed содержит четыре массива индивидуальных исходов, хеши весов обеих эпох и точные значения метрик. Первичный парный результат R21 относится к dev500. При совпадении выбранных весов полный dev воспроизводит тот же тест для Dense и factor. Сравнение с графовой моделью требует отдельного запуска её обучения и выбора эпохи на 580 dev.","","[Протокол](PROTOCOL_RU.md) · [Исходный R21](../REPORT_RU.md)"])
    (D/"REPORT_RU.md").write_text("\n".join(lines)+"\n",encoding="utf8")


if __name__=="__main__":
    if sys.argv[1]=="plan": plan()
    elif sys.argv[1]=="fit": fit(int(sys.argv[2]))
    elif sys.argv[1]=="select": select(int(sys.argv[2]))
    elif sys.argv[1]=="report": report()


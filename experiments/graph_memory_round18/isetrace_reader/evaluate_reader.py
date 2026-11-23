"""Score sealed block-opening actions against official character spans and report paired reader effects."""
from collections import Counter
from pathlib import Path
from statistics import mean
import json
import sys

import reader as r
from score import compare
from verify_package import evaluate

def evaluate_panel(path,truth,results):
    seal=r.load(path/"response-lock.json")
    assert r.pilot.sha(path/"open-receipts.jsonl")==seal["responses"] and r.pilot.sha(path/"panel-lock.json")==seal["panel"]
    plan=r.load(path/"panel.json.gz");control={}
    log={v["prompt_sha256"]:v for v in (json.loads(a) for a in (path/"open-receipts.jsonl").read_bytes().splitlines())}
    assert len(log)==seal["attempts"]
    for q,rec in plan.items():
        assert q not in results
        g=truth[q];sources={(s["event_id"],s["json_pointer"]) for s in g};gold_model=tuple(r.pilot.SourceSpan.model_validate(s) for s in g)
        def native(fragments):
            nodes=tuple(r.pilot.RankedNodeRecord(node_id=z["node"],score=0,token_count=z["token_count"],source_spans=tuple(r.pilot.SourceSpan.model_validate(s) for s in z["spans"])) for z in fragments)
            m=r.pilot.span_metrics_under_token_budget(nodes,gold_model,2048)
            fs,c,d=evaluate(g,[s for z in fragments for s in z["spans"]])
            assert all(abs(a-b)<1e-12 for a,b in ((fs,m.full_support),(c,m.coverage),(d,m.density)))
            return dict(full_support=int(fs),coverage=c,density=d)
        result={}
        for label,v in rec["arms"].items():
            fragments={z["id"]:z for z in v["fragments"]};logrow=log[v["prompt_sha256"]]
            selected=([fragments[logrow["selected"]]] if logrow["valid"] else [])
            assert not selected or selected[0]["text_sha256"]==logrow["opened_sha256"]
            oracle=max((native([z]) for z in v["fragments"]),key=lambda m:(m["full_support"],m["coverage"],m["density"]))
            result[label]={"qwen":native(selected),"bm25":native([fragments[v["bm25_id"]]]),"oracle_one":oracle,"all_fragments":native(v["fragments"]),
                           "selected":logrow["selected"],"confirmed_open":bool(selected),"e5_tokens":v["e5_tokens"],
                           "prompt_tokens":logrow["usage"]["prompt_tokens"],"completion_tokens":logrow["usage"]["completion_tokens"],
                           "opened_e5":selected[0]["token_count"] if selected else 0,"fragments":len(fragments)}
        control[q]={"t":rec["t"],"gold_sources":len(sources),"gold_spans":len(g),"arms":result}
    results.update(control)
    return control
def summarize(rows):
    result={"n":len(rows),"gold_sources":dict(Counter(v["gold_sources"] for v in rows.values())),"metrics":{},"paired":{}}
    for h in ("related","value"):
        selected=[rec["arms"][h] for rec in rows.values()]
        methods={}
        for m in ("qwen","bm25","oracle_one","all_fragments"):
            methods[m]={"full_count":sum(a[m]["full_support"] for a in selected),"coverage":mean(a[m]["coverage"] for a in selected),
                        "density":mean(a[m]["density"] for a in selected)}
        methods["confirmed_open"]=sum(a["confirmed_open"] for a in selected)
        for k in ("e5_tokens","opened_e5","prompt_tokens","completion_tokens","fragments"):methods[k]=mean(a[k] for a in selected)
        for source_count in result["gold_sources"]:
            subset=[v["arms"][h] for v in rows.values() if v["gold_sources"]==source_count]
            methods[f"sources_{source_count}"]={m:sum(a[m]["full_support"] for a in subset) for m in ("qwen","bm25","oracle_one","all_fragments")}
        result["metrics"][h]=methods
    def view(label,m):return {q:{"t":v["t"],"full_support":v["arms"][label][m]["full_support"]} for q,v in rows.items()}
    for m in ("qwen","bm25","oracle_one","all_fragments"):
        result["paired"][m+"_related_minus_value"]=compare(view("related",m),view("value",m))
    for arm in ("related","value"):
        result["paired"]["qwen_minus_bm25_"+arm]=compare(view(arm,"qwen"),view(arm,"bm25"))
    return result
def report(s):
    notes=["# Нативный Qwen выбирает один подтверждающий фрагмент графовой памяти","",
           "Из предложенных фрагментов истории инструментальных вызовов читатель мог открыть один по ID. Успех означает покрытие выбранным блоком всех эталонных символов. Сравниваются две упаковки BM25 при бюджете 2 048 E5-токенов. Related добирает парную сторону уже попавшего в префикс вызова, value добирает по баллу BM25 / √стоимости. Условия используют один вопрос, стабильные ID, хронологическое представление фрагментов и одинаковое задание. Текстовый ранжировщик формирует кандидатов, действие выполняет локальный Qwen3.8-27B-UD-Q4_K_M (llama.cpp b12441; NVIDIA RTX 3090).",
           "", "| Панель | Упаковка | Нативный open | Первый BM25 | Лучший возможный один | Полный видимый набор | Фактически открыто |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for label,title in (("different","Выдачи различаются"),("same","Выдачи идентичны"),("combined","Итого по двум панелям")):
        d=s[label];n=d["n"]
        for arm,a in d["metrics"].items():
            counts=[a[m]["full_count"] for m in ("qwen","bm25","oracle_one","all_fragments")]
            notes.append(f"| {title} | {arm} | "+" | ".join(f"{k}/{n}" for k in counts)+f" | {a['confirmed_open']}/{n} |")
    d=s["different"];pd=d["paired"]["qwen_related_minus_value"];lo,hi=pd["trajectory_bootstrap_ci95"]
    notes.extend(["",f"На основной условной панели Qwen выиграл для related у value в {pd['full_wins']} вопросах и уступил в {pd['full_losses']}. Разность составляет {100*pd['delta']:+.2f} п.п., 95% описательный интервал bootstrap по траекториям [{100*lo:+.2f} … {100*hi:+.2f}]. Обе политики могли прочитать одинаковые вопросы и находятся под одним лимитом. Точность локализации моделью ниже достижимого уровня в тех случаях, когда один из выданных блоков содержит все доказательства, но модель выбирает другой.",
           "","| Основная панель | Полное подтверждение при наличии подходящего блока | Qwen Coverage, % | Набор, E5-токены | Выбранный блок, E5-токены | Полный вход, Qwen-токены |",
           "|---|---:|---:|---:|---:|---:|"])
    for arm,a in d["metrics"].items():
        notes.append(f"| {arm} | {a['qwen']['full_count']}/{a['oracle_one']['full_count']} | {100*a['qwen']['coverage']:.2f} | {a['e5_tokens']:.1f} | {a['opened_e5']:.1f} | {a['prompt_tokens']:.1f} |")
    for label,title in (("different","основной"),("same","контрольной")):
        dist=", ".join(f"{k} исходное поле — {v}" for k,v in s[label]["gold_sources"].items())
        notes.extend(["",f"На {title} панели число вопросов по количеству исходных полей в эталоне: {dist}. Раздельные показатели по исходным полям и по методам включены в [результаты](results.json)."])
    notes.extend(["", "Исходная выборка — новые относительно R17 прямые вопросы официального теста ISETrace. Первичная страта содержит все 27 траекторий, прошедших строгие предметные фильтры с разными наборами фрагментов. Контроль включает все 9 допустимых траекторий с совпадающей выдачей за пределами первичной страты. Для совпадающих контекстов выполнен один запрос модели на траекторию. После блокировки 63 предсказаний загружены эталонные координаты. Числа относятся к двум условным панелям. Точность свободного ответа, перенос на другие темы и преимущество над обученным R-GCN здесь не измерялись. [Первичный протокол](PROTOCOL_RU.md) · [Условие равной выдачи](CONTROL_PROTOCOL_RU.md) · [Воспроизводимость](REPRODUCE_RU.md)"])
    (r.ROOT/"REPORT_RU.md").write_text("\n".join(notes)+"\n",encoding="utf8",newline="\n")
def main():
    paths=(r.ROOT,r.ROOT/"matched_controls")
    assert all((p/"response-lock.json").is_file() for p in paths)
    gold=r.load(r.OFF/"gold-spans.json.gz")
    all_rows={};group={}
    for tag,p in zip(("different","same"),paths):
        group[tag]=evaluate_panel(p,gold,all_rows)
    group["combined"]=all_rows;summary={k:summarize(x) for k,x in group.items()}
    assert summary["same"]["paired"]["qwen_related_minus_value"]["delta"]==0
    r.save(r.ROOT/"outcomes.json.gz",all_rows);r.save(r.ROOT/"gold-panel-spans.json.gz",{q:gold[q] for q in all_rows})
    r.save(r.ROOT/"results.json",summary);report(summary)
    names=sorted(p for p in r.ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="MANIFEST_SHA256.json")
    r.save(r.ROOT/"MANIFEST_SHA256.json",{p.relative_to(r.ROOT).as_posix():r.pilot.sha(p) for p in names})
    print(len(names),sum(p.stat().st_size for p in names),r.pilot.sha(r.ROOT/"MANIFEST_SHA256.json"))
    print({k:{a:v["qwen"]["full_count"] for a,v in d["metrics"].items()} for k,d in summary.items()})
if __name__=="__main__":main()

"""Publish a fixed report and phase-specific checksums when the entire phase has completed."""
from pathlib import Path
import json,hashlib
D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def val(n):return f"{100*n:.2f}".replace(".",",")
def ci(a):return "["+"; ".join(val(x) for x in a)+"]"
def publish(mode):
    r=read(D/f"{mode}-complete.json");modern="R35_oof_3894";names=["R35_oof_3894","R33_cost_worst","full_rgcn","wo_chunk_adjacency"]
    lines=["# "+("Штатное сравнение пяти инициализаций" if mode=="canonical" else "Сравнение после выбора эпох по бюджетным метрикам"),"",
        "Сопоставлены 2 000 фиксированных вопросов из 1 207 траекторий на общих Dense-FT seed 13, 17, 29, 37 и 41. Пара 37/41 зафиксирована до наблюдения результатов соответствующих нативных графов.","",
        "| Seed | R35 FS@2048 | R33 | Полный R-GCN | Без chunk adjacency |","|---|---:|---:|---:|---:|"]
    for s,v in r["five"]["per_seed_means"].items():lines.append("| "+s+" | "+" | ".join(val(v[k][0]) for k in names)+" |")
    lines+=["","| Выборка | Соперник | Разница FS, п.п. | 95% ДИ по траекториям | 95% ДИ по траекториям и seed |","|---|---|---:|---:|---:|"]
    for name,panel in [("Пять seed",r["five"]),("Заранее отложенные 37/41",r["forward"])]:
        for m in names[2:]:
            e=panel["comparisons"][modern+"/"+m]["full_support_2048"]
            lines.append("| "+" | ".join([name,m,val(e["delta"]),ci(e["conditional_ci"]),ci(e["crossed_ci"])])+" |")
    lines+=["","Полный критерий по пяти seed: "+("обе нижние границы при обоих способах перевыборки положительны." if r["five"]["both_lower_bounds_positive_in_both_intervals"] else "условие положительности всех четырёх нижних границ не выполнено."),
            "Направленный перенос на 37/41: "+("обе средние разницы положительны." if r["forward"]["both_positive_points"] else "условие двух положительных точечных оценок не выполнено."),
            "Интервальный критерий для 37/41: "+("выполнен." if r["forward"]["both_lower_bounds_positive_in_both_intervals"] else "как минимум одна нижняя граница не выше нуля."),"",
            "Две процедуры выбора графовой эпохи оцениваются отдельно. Для утверждения об устойчивости к процедуре выбора нужен результат обеих серий. Известность тестовых вопросов и трёх ранее наблюдавшихся seed учитывается в интерпретации. [Протокол](PROTOCOL_RU.md) · [Все шесть метрик и интервалы]("+mode+"-complete.json)"]
    rp=D/f"REPORT_{mode}.md";text="\n".join(lines)+"\n"
    if rp.exists():assert rp.read_text(encoding="utf8")==text
    else:rp.write_text(text,encoding="utf8",newline="\n")
    namesf=["plan.json","implementation.json","PROTOCOL_RU.md","pipeline.py","report.py","verify.py",rp.name,mode+"-complete.json"]
    for s in (13,17,29,37,41):namesf+=[f"{mode}-{s}.json.gz",f"{mode}-receipt-{s}.json"]
    snap={n:sha(D/n) for n in namesf};mfile=D/f"{mode}-manifest.json"
    if mfile.exists():assert snap==read(mfile)
    else:mfile.write_text(json.dumps(snap,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8",newline="\n")

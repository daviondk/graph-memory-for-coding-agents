"""Summarize predeclared pair comparisons, exact native cost and the portion of input changed."""
from collections import defaultdict
from statistics import mean, median
from tail import D,E5,FT,load,put,pilot

def describe(name):
    stat=load(name+"-results.json")
    rows=load(name+"-outcomes.json.gz");details=defaultdict(list)
    for i in range(8):
        for r in load(f"{name}-picks-{i}.json.gz"):
            for q,rec in r["q"].items():
                details["remaining_after_core"].append(rec["remaining"])
                details["common_prefix_n"].append(len(rec["prefix"]))
                details["whole_partners_n"].append(len(rec["core"])-len(rec["prefix"]))
                details["related_extra_n"].append(len(rec["related"])-len(rec["core"]))
                for method in ("a","b","c"):
                    details[method+"_fine_n"].append(len(rec["fine"][method]))
    out={k:dict(mean=mean(d),median=median(d),nonzero=sum(bool(x) for x in d)) for k,d in details.items()}
    out["equal_full_support_outcome_b_vs_a"]=sum(r["a"]["full_support"]==r["b"]["full_support"] for r in rows.values())
    return out
def report():
    scopes=("frozen","trained");desc={k:describe(k) for k in scopes};put("selection-diagnostics.json",desc)
    notes=["# Чем заполнить остаток бюджета чтения после извлечения связанных свидетельств","",
           "Две модели независимо ранжируют исходные аргументы и результаты инструментальных вызовов в тех же 2 000 вопросах ISETrace. Все методы сохраняют рекомендованный моделью префикс целых узлов. Контроль related затем поднимает целые фрагменты противоположной роли из вызовов префикса и добирает остальные целые узлы. Альтернативы удерживают префикс и помещающихся партнёров и заменяют только последнюю стадию блоками около 64 WordPiece-токенов. Каждый такой блок целиком принадлежит ранжированному исходному узлу. Уже прочитанные символы исключаются.",
           "", "| Скорер и метод | Полные подтверждения / 2 000 | Full Support, % | Coverage, % | Density, % | Среднее число E5-токенов |","|---|---:|---:|---:|---:|---:|"]
    names={"prefix":"Авторский префикс","core":"Префикс + целые партнёры","related":"Контроль, только целые узлы","a":"A, порядок фрагментов в родителе","b":"B, лексика внутри родителя","c":"C, RRF60 по двум рангам"}
    scores={"frozen":"frozen E5-base-v2","trained":"Dense-FT, один seed"}
    for mod in scopes:
        res=load(mod+"-results.json")
        for p,tag in names.items():
            val=res["stats"][p]
            notes.append((f"| {scores[mod]}, {tag} | {val['full']} | {100*val['full']/2000:.2f} | {100*val['coverage']:.2f} | {100*val['density']:.2f} | {val['tokens']:.1f} |").replace(".",","))
    notes.extend(["","| Скорер | Сравнение | Выигрыши / потери по Full Support | Δ Full Support, п.п. [95% ДИ] | Δ Coverage, п.п. [95% ДИ] |","|---|---|---:|---:|---:|"])
    for mod in scopes:
        rs=load(mod+"-results.json")
        for p,tag in (("b-related","Основной B − related"),("a-related","A − related"),("c-related","C − related"),("b-a","B − A"),("c-b","C − B"),("b-prefix","B − префикс")):
            v=rs["pairs"][p]
            def interval(k):
                e=v["differences"][k];lo,hi=e["cluster_ci95"]
                return f"{100*e['estimate']:+.2f} [{100*lo:+.2f} … {100*hi:+.2f}]"
            notes.append((f"| {scores[mod]} | {tag} | {v['fs_wins']} / {v['fs_losses']} | {interval('full_support')} | {interval('coverage')} |").replace(".",","))
    for mod in scopes:
        val=desc[mod];stat=load(mod+"-results.json")
        b=stat["stats"]["b"];ref=stat["stats"]["related"];c=stat["stats"]["c"]
        notes.extend(["",f"**{scores[mod]}.** После общего префикса и целых связанных узлов оставалось в среднем {val['remaining_after_core']['mean']:.1f} токена. Основной B дал {b['full']} полных комплектов против {ref['full']} у контроля. Вариант C, объединяющий ранги крупного родителя и лексическую позицию мелкого блока с RRF60, дал {c['full']} комплектов. Его Coverage — {100*c['coverage']:.2f}% против {100*ref['coverage']:.2f}% у related."])
        oracle=load(mod+"-oracle.json");loss=oracle["b_losses_against_related"]
        notes.extend(["",f"Диагностика по известным эталонным интервалам даёт достижимый максимум {oracle['fine_oracle_full']}/2 000 при том же общем префиксе, цене и допустимом множестве мелких блоков. Среди {sum(loss.values())} потерь B относительно related в {loss.get('reachable',0)} случаях существовал подходящий по бюджету другой выбор мелких блоков. В {loss.get('intersects_core',0)} случаях требуемый блок пересекался с уже прочитанным узлом, в {loss.get('cost',0)} случаях сумма его минимально необходимых затрат превышала остаток. [Постфактум-разложение предельной достижимости](ORACLE_NOTE_RU.md)"])
    notes.extend(["","Первичная проверка — B−related по Full Support. A и C были указаны до запуска, результаты по обеим метрикам и обоим эмбеддерам приведены целиком. Полное покрытие эталона чувствительно к потере последнего необходимого символа. Переход на мелкую единицу может повысить число попавших в контекст символов и одновременно исключить целый крупный фрагмент. Интервалы описательные, кластерный bootstrap по 1 207 траекториям, 10 000 выборок. Публикационный trained baseline усредняется по пяти seed; здесь сравниваются методы упаковки на одном локально обученном ранжировщике.",
                  "","Блоки покрывают все исходные события, для которых выпущены PU. На каждую оценку предвычисляется локальная статистика BM25 по всем мелким блокам текущей траектории, что несёт дополнительные издержки CPU и хранения индекса. Доставка текста ограничена 2 048 токенами. Ранее перекрывающиеся PU в авторском префиксе и его целых партнёрах оплачиваются по цене каждого узла. Мелкие блоки попарно неперекрывающиеся и не дублируют их исходные символы. [Диагностика состава](selection-diagnostics.json) · [Заранее установленный протокол](PROTOCOL_RU.md) · [Порядок повторения](REPRODUCE_RU.md)"])
    (D/"REPORT_RU.md").write_text("\n".join(notes)+"\n",encoding="utf8",newline="\n")
    fn=sorted(p for p in D.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name!="MANIFEST_SHA256.json")
    put("MANIFEST_SHA256.json",{p.relative_to(D).as_posix():pilot.sha(p) for p in fn})
    print(len(fn),sum(p.stat().st_size for p in fn),pilot.sha(D/"MANIFEST_SHA256.json"))
if __name__=="__main__":report()

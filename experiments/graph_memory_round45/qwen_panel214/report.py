"""Render a table-driven report after primary and additional sealed analyses are complete."""
from common import *

NAMES={"qwen":"Qwen3-Embedding-8B","qwen_seen":"Qwen, просмотренное в конце",
       "r39_no_observed":"R39 без прямого признака просмотра","r39_no_observed_seen":"Та же R39, просмотренное в конце",
       "R39":"R39, обученная с признаком просмотра","bge":"BGE","bge_seen":"BGE, просмотренное в конце",
       "union":"union_cost","union_seen":"union_cost, просмотренное в конце"}
FUSION={"qwen":"Qwen","qwen_seen":"Qwen, просмотренное в конце","r39":"RRF Qwen + R39","r39_seen":"RRF Qwen + R39, просмотренное в конце",
        "bge":"RRF Qwen + BGE","bge_seen":"RRF Qwen + BGE, просмотренное в конце","union":"RRF Qwen + union_cost","union_seen":"RRF Qwen + union_cost, просмотренное в конце"}


def num(n,digits=2):
    return f"{n:.{digits}f}".replace(".",",")


def delta(v,metric=0,macro=False):
    key="macro" if macro else "delta"
    ci="macro95" if macro else "ci95"
    sign="+" if v[key][metric]>0 else ""
    return f"{sign}{num(100*v[key][metric])} п.п. [{num(100*v[ci][0][metric])}; {num(100*v[ci][1][metric])}]"


def table(panel,path,names):
    lines=["| Метод | MSS@5 | MSS@8 | 2 048 | 6 144 | GroupRecall@5 | GroupRecall@8 | Necessity@5 | Возвращено токенов @5 / @8 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for method in path:
        row=panel["methods"][method]
        cells=[*map(str,row["complete_counts"]),*(num(100*x)+"%" for x in row["micro"][4:])," / ".join(num(x,0) for x in row["returned_tokens"][:2])]
        lines.append("| "+names[method]+" | "+" | ".join(cells)+" |")
    return "\n".join(lines)


def claims(t,key,metrics=(0,1,2)):
    v=t["contrasts"][key]
    return ", ".join(f"{label} {delta(v,i)}" for i,label in zip(metrics,("MSS@5","MSS@8","при 2 048")))


def main():
    r=read(OUT/"results.json");f=read(OUT/"fusion-results.json");g=read(OUT/"gpu-seal.json");p=read(OUT/"panel.json")
    primary=r["panels"]["outside204"];combo=f["panels"]["outside204"]
    k="r39_no_observed_seen minus qwen_seen";v=primary["contrasts"][k]
    fk="r39_seen minus qwen_seen";z=combo["contrasts"][fk]
    qs=r["resources"]["all214"];pstate=g["matched_pilot"]
    lines=[
      "# Получение достаточного контекста на 214 состояниях SERBench",
      f"На 204 состояниях вне пилота R39 без собственного признака просмотра с общей отсрочкой ранее прочитанных фрагментов собрала полный набор в первых пяти единицах в **{primary['methods']['r39_no_observed_seen']['complete_counts'][0]}/204** случаях. Сильный семантический контроль Qwen3-Embedding-8B с тем же правилом достиг **{primary['methods']['qwen_seen']['complete_counts'][0]}/204**. Предопределённая парная разность составляет **{delta(v)}**, {v['wins'][0]} выигрышей и {v['losses'][0]} потерь. При равном весе репозитория разность {delta(v,macro=True)}.",
      "## Протокол",
      "Из 214 состояний удержанной части публичной Cal500 исходные десять входили в предшествующий выборочный пилот. Расширение на остальные 204 и основной контраст заданы до расчёта их Qwen-оценок. В обоих множествах представлены 69 репозиториев. Обучение R39 использовало 179 состояний других репозиториев, веса выбирались на 101 dev. Все девять методов получили одни входы и один полный пул. В дополнительных четырёх маскированных вариантах общая операция отодвигает просмотренные фрагменты в конец с сохранением порядка остальных.",
      "Микроусреднение взвешивает каждое состояние одинаково. 95%-е интервалы получены из 10 000 парных bootstrap-выборок целых репозиториев, которые сохраняют взаимозависимость состояний. Первые четыре столбца — числа полных достаточных наборов. 2 048 и 6 144 означают непрерывный префикс восьми целых единиц под токенным ограничением, остальные три колонки представляют официальные метрики в процентах.",
      "## Основные результаты на 204 состояниях вне пилота",
      table(primary,NAMES,NAMES),
      "Сопоставление без прямого признака просмотренности и без постфильтра относительно Qwen даёт "+claims(primary,"r39_no_observed minus qwen")+". При согласованной отсрочке получены "+claims(primary,k)+".",
      "При наличии ранее просмотренных кандидатов разность главного сравнения на MSS@5 составляет "+delta(r["panels"]["outside204_overlap"]["contrasts"][k])+", при их отсутствии "+delta(r["panels"]["outside204_no_overlap"]["contrasts"][k])+". Разрез описательный: распределение стадий агента в этих двух подмножествах различается.",
      "## Полная локальная отложенная часть (214)",
      table(r["panels"]["all214"],NAMES,NAMES),
      "## Дополнительное слияние рангов",
      f"До новых результатов Qwen отдельно зафиксировали равновесную сумму reciprocal ranks с константой 60. На 204 состояниях RRF Qwen + R39 с той же отсрочкой даёт {combo['methods']['r39_seen']['complete_counts'][0]}/204 на MSS@5, разность с Qwen **{delta(z)}** ({z['wins'][0]} выигрышей, {z['losses'][0]} потерь). На MSS@5 разности с двумя аналогичными слияниями составляют {delta(combo['contrasts']['r39_seen minus bge_seen'])} относительно Qwen + BGE и {delta(combo['contrasts']['r39_seen minus union_seen'])} относительно Qwen + union_cost. Положительный результат относительно Qwen требует этих контролей для атрибуции добавочной ценности памяти. [Первоисточник формулы RRF](https://cormack.uwaterloo.ca/cormack/cormacksigir09-rrf.pdf)",
      table(combo,FUSION,FUSION),
      "## Контроль численного повтора и стоимость",
      f"Повторный прогон десяти пилотных состояний совпал по обеим top-8 выдачам для {sum(v['sameLists'] for v in pstate.values())}/10. Максимальная разность косинусов между двумя GPU-прогонами {max(v['maxCosDifference'] for v in pstate.values()):.8f}. Во всех случаях совпали токенизация и состав полных пулов. Все 214 Qwen-предсказаний получены в одном GPU-режиме. Полный прогон обработал {qs['candidates']:,} кандидатов, {qs['strings']:,} строк, {qs['tokens']:,} входных токенов. Усечены {qs['truncated']:,} строки ({num(100*qs['truncated']/qs['strings'])}%). Сумма времени обработки состояний {num(qs['seconds']/60,1)} мин, без подготовки весов и вычисления оценочных метрик.",
      "Проверена GGUF Q4_K_M-версия Qwen3-Embedding-8B при 512 входных токенах и собственном формировании запроса. Авторский Qwen3-Reranker-8B и многошаговый MSS-Complement здесь не использовались. Публичная панель Cal500 и закрытая Test500 имеют разные репозитории, поля истории и частоту отмеченных просмотренных единиц. Эффективность на Test500 и на реальной успешности решения задач из этих экспериментов не следует. [SERBench v3](https://arxiv.org/abs/2609.20050v3) · [Точная ревизия Qwen](https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF/tree/69d0e58a13e463cd99a9b83e3f5fee7c10265fab)"
    ]
    (OUT/"REPORT_RU.md").write_text("\n\n".join(lines)+"\n",encoding="utf8")


if __name__=="__main__":main()

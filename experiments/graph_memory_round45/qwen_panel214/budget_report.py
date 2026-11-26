"""Generate the documented secondary budget comparison and resource table."""
from common import *
def fmt(v,precision=2):return f"{v:.{precision}f}".replace(".",",")
LABEL={"base/r39_no_observed_seen":"R39 с общей отсрочкой","base/qwen_seen":"Qwen с общей отсрочкой","base/r39_no_observed":"R39","base/qwen":"Qwen",
       "fusion/r39_seen":"RRF Qwen + R39 с отсрочкой","fusion/bge_seen":"RRF Qwen + BGE с отсрочкой","fusion/union_seen":"RRF Qwen + union_cost с отсрочкой","base/bge_seen":"BGE с отсрочкой","base/union_seen":"union_cost с отсрочкой"}
def main():
    v=read(OUT/"budget-results.json");tab=v["panels"]["outside204"];answers=read(OUT/"results.json")
    a,b="base/r39_no_observed_seen","base/qwen_seen";aa,bb=[tab["methods"][x] for x in (a,b)]
    diff=tab["contrasts"][a+" minus "+b];ct=v["budgets"]
    table=["| Общий потолок | R39 — полные наборы / 204 | Qwen — полные наборы / 204 | R39 — средний расход | Qwen — средний расход |","|---:|---:|---:|---:|---:|"]
    for j,k in enumerate(ct):table.append(f"| {k:,} | {aa['counts'][j]} | {bb['counts'][j]} | {fmt(aa['mean_tokens'][j],0)} | {fmt(bb['mean_tokens'][j],0)} |")
    t2=["| Фиксированная система | Площадь, % | Полных при 2 048 (средний расход) | Полных при 6 144 (средний расход) |","|---|---:|---:|---:|"]
    for name,label in LABEL.items():
        rec=tab["methods"][name]
        cells=["%d (%s)"%(rec["counts"][ct.index(k)],fmt(rec["mean_tokens"][ct.index(k)],0)) for k in (2048,6144)]
        t2.append("| "+label+" | "+fmt(100*rec["auc"])+" | "+" | ".join(cells)+" |")
    t3=["| Контраст по площади | Разница, п.п. | 95%-й парный интервал по репозиториям | Выигрыши / потери по состояниям |","|---|---:|---|---:|"]
    for key,z in tab["contrasts"].items():
        a1,b1=key.split(" minus ");l,h=z["micro_ci"]
        t3.append(f"| {LABEL[a1]} минус {LABEL[b1]} | {fmt(100*z['delta'])} | [{fmt(100*l)}; {fmt(100*h)}] | {z['wins']} / {z['loss']} |")
    l,h=diff["micro_ci"];j=ct.index(2048)
    parts=["# Сравнение при одинаковом токенном бюджете",
        f"На 204 состояниях SERBench Cal500 вне пилота при одинаковом пределе в 2 048 токенов и общей отсрочке просмотренных единиц полное множество свидетельств вошло в {aa['counts'][j]} пакетов R39 и {bb['counts'][j]} пакетов Qwen. Средние фактические расходы составили {fmt(aa['mean_tokens'][j],0)} и {fmt(bb['mean_tokens'][j],0)} токенов. Стоимость вычисления эмбеддингов учитывается отдельно. [Основной отчёт](REPORT_RU.md)",
        f"При общем равномерном бюджете от 0 до 6 144 токенов разность средней вероятности получить полный набор составила {fmt(100*diff['delta'])} п.п. [{fmt(100*l)}; {fmt(100*h)}] для R39 минус Qwen. Эта площадь определяется наименьшей стоимостью достаточного префикса заранее фиксированной выдачи до восьми единиц. Все точки и контрасты зафиксированы до оценки новых исходов. [Протокол](BUDGET_AUDIT_RU.md)",
        "\n".join(table),"## Контрольные системы при тех же бюджетах","\n".join(t2),"\n".join(t3),
        "Ограничение одинаково для всех систем. Когда следующая целая единица превышает доступный остаток, читатель останавливается. Поэтому системы с одинаковым потолком расходуют разное число токенов. Метрика площади предполагает равномерный спрос на бюджет, а 2 048 и 6 144 — конкретные фиксированные пределы. Данные по полной панели 214, сгруппированные интервалы и пороги для каждого состояния доступны отдельно. [Детальные результаты](budget-results.json) · [Пороги и фактические затраты](budget-thresholds.json.gz)"]
    (OUT/"BUDGET_REPORT_RU.md").write_text("\n\n".join(parts)+"\n",encoding="utf8")
if __name__=="__main__":main()

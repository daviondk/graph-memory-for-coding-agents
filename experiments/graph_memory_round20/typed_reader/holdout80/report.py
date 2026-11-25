"""Turn immutable holdout comparisons into a short, reversible study report."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def fmt(x):return f"{100*x:.2f}".replace(".",",")
def interval(r):return f"{fmt(r['delta'])} [{fmt(r['ci'][0])} … {fmt(r['ci'][1])}]"
def main():
    data=json.loads((HERE/"results.json").read_bytes())
    text=["# Структурное ранжирование на дополнительных вопросах",
          "Эти 80 вопросов отсутствуют среди 500 вопросов выбора Dense-checkpoint и калибровки dev-варианта. Все 74 исходные траектории отделены от original train, а 21 из них отсутствует и в dev500. Каждый граф вычислен по нативному адаптеру ISETrace. Веса каждого варианта заморожены до получения новых рангов. Основной вариант обучен по исходным BM25-рангам на исходном train и затем перенесён на Dense-FT. Вариант с 500 вопросами dev имеет дополнительное обучение на части того же раздела."]
    for gr,title in (("all","Все 80 вопросов"),("novel","Новые траектории относительно dev500"),("shared","Общие траектории с dev500")):
        v=data[gr+"/prefix"]; means=v["means"]; pairs=v["pairs"];n=means["dense"]["n"]
        tab=["| Вариант | Полное свидетельство | Coverage | Δ Full Support к Dense, п.п. [95% ДИ] | Выигрыши / потери |",
             "|---|---:|---:|---:|---:|",
             f"| Dense-FT | {means['dense']['hits']} / {n} | {fmt(means['dense']['coverage'])}% | — | — |"]
        for arm in ("train/role_degrees","train/degrees","train/role","train/typed","train/shuffled","dev/role_degrees","dev/typed","dev/shuffled"):
            m=means[arm]; pair=pairs[arm+"-dense"]["full_support"]
            tab.append(f"| {arm} | {m['hits']} / {n} | {fmt(m['coverage'])}% | {interval(pair)} | {pair['win']} / {pair['loss']} |")
        text.extend(["## "+title,"\n".join(tab)])
        c=pairs["train/typed-shuffled"]["full_support"];d=pairs["train/role_degrees-dense"]["full_support"]
        text.append(f"Первичная пара включает {d['q']} вопросов и {d['clusters']} кластеров. Разность между поправками по настоящим и перемешанным соседям при сохранении степеней равна {interval(c)} п.п. Обучение обеих поправок проводилось только на original train.")
    text.extend(["Префикс целых узлов останавливается, когда следующее свидетельство не помещается в 2 048 токенов. Все контрольные варианты, ранжирование с добором, количество узлов и интервалы по Coverage сохранены в машинной таблице. Неопределённость соответствует 10 000 парным бутстреп-перевыборкам траекторий. Эта панель остаётся частью того же ISETrace. [Полные оценки](results.json) · [Результаты по вопросам](outcomes.json.gz) · [Сквозная проверка исходного плотного ранга](../../untuned_holdout/REPORT_RU.md)",
                 "[Предварительная постановка](PROTOCOL_RU.md) · [Хеши исходных графов](source-plan.json) · [Прогнозы до разметки](forecast-seal.json)"])
    (HERE/"REPORT_RU.md").write_text("\n\n".join(text)+"\n",encoding="utf8")
    root=HERE.parent/"REPORT_RU.md"; existing=root.read_text(encoding="utf8")
    marker="## Перенос на дополнительные вопросы"
    if marker not in existing:
        primary=data["all/prefix"]["means"]
        p=data["all/prefix"]["pairs"]["train/role_degrees-dense"]["full_support"]
        root.write_text(existing.rstrip()+"\n\n"+marker+"\n\n"+f"На 80 вопросах вне официальных dev500 замороженное train-правило ранга, роли и степеней полностью покрывает {primary['train/role_degrees']['hits']} против {primary['dense']['hits']} у Dense-FT, Δ {interval(p)} п.п. Группировка по 74 траекториям. [Все варианты и отдельная проверка 21 новой траектории](holdout80/REPORT_RU.md)\n",encoding="utf8")
if __name__=="__main__":main()


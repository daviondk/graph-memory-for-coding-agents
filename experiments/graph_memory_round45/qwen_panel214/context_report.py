"""Append the measured information-access contract and cost-curve pointers to the main report."""
from common import *
def main():
    target=OUT/"REPORT_RU.md";input_contract=read(OUT/"input-contract.json")["panels"]["outside204"];ql=read(OUT/"qwen-scores.json.gz");p=read(OUT/"panel.json");qs=p["remaining"]
    key="## Доступ систем к состоянию и стоимость выдачи"
    text=target.read_text(encoding="utf8").partition("\n"+key)[0].rstrip();s=input_contract["present"]
    qlen=[ql[q]["lengths"][0] for q in qs];doclen=[l for q in qs for l in ql[q]["lengths"][1:]]
    comp=read(OUT/"fusion-results.json")["panels"]["outside204"]["contrasts"]
    from report import delta
    extra=f"""\n\n{key}

Все системы ранжировали одни и те же пулы кандидатов в одних и тех же состояниях, с одинаковой отсрочкой просмотренных единиц в парном основном сравнении. Читатель использует неизменный порядок целых единиц при тех же верхних пределах 2 048 и 6 144 токена. Отдельно показаны фактический расход каждого метода, качество при девяти бюджетах и точная площадь кривой до 6 144 токенов. [Бюджетная проверка](BUDGET_REPORT_RU.md)

В запрос Qwen переданы три публичных поля — information_need, current_subgoal и issue, каждое заполнено на 204/204. Обучаемому R39 доступны дополнительные поля. На той же панели current_observation присутствовало в {s['current_observation']} случаях, current_hypothesis в {s['current_hypothesis']}, search_queries в {s['search_queries']}, opened_files в {s['opened_files']}, latest_test_output и current_diff ни разу. На входе эмбеддинга усечены {sum(l>512 for l in qlen)}/{len(qlen)} запросов и {sum(l>512 for l in doclen)}/{len(doclen)} описаний кандидатов. Частота заполнения не даёт величину дополнительной информации и не учитывает повтор контента между полями. Сравнение оценивает системы с этими входными представлениями; конкретный механизм отбора при идентичном информационном входе потребует отдельной проверки. [Контроль на идентичном видимом тексте](MATCHED_REPORT_RU.md) · [Контракт входов](input-contract.json)

При 2 048 токенах дополнительное слияние Qwen + R39 имело {delta(comp['r39_seen minus bge_seen'],2)} относительно Qwen + BGE, {delta(comp['r39_seen minus union_seen'],2)} относительно Qwen + union_cost и {delta(comp['r39_seen minus qwen_seen'],2)} относительно одной Qwen. Все три сравнения используют общую отсрочку. Первое различие наблюдается в дополнительной системе на конкретном бюджете; приведены индивидуальные интервалы без поправки на многочисленные вторичные метрики.

Для независимого пересчёта сохранены исходные порядки, длины единиц и числовая проекция официальных групп, минимальных количеств и допустимых альтернатив. Две программы стандартной библиотеки Python заново рассчитывают все семь показателей и проверяют точную интегральную стоимость каждой выдачи. [Проверка метрик](verify_metrics.py) · [Проверка бюджета](verify_budget.py)
"""
    target.write_text(text+extra,encoding="utf8")
if __name__=="__main__":main()

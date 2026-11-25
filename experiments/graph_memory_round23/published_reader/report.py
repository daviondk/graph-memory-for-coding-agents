"""Generate the Russian report directly from signed paired results."""
import gzip
import json
import hashlib
from pathlib import Path
D=Path(__file__).parent
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def fmt(x,d=2):return f'{x:.{d}f}'.replace('.',',')
def delta(comp):
    v=comp['diff']['full'];l,r=v['ci95']
    return f"{fmt(100*v['estimate'])} п. п. (95% ДИ {fmt(100*l)} … {fmt(100*r)})"
def report():
    from verify_equal import check
    for partition in ('dev','test'):check(partition)
    res=load(D/'test-results.json');equal=load(D/'test-equal-spend-results.json');assert equal['n']==res['n']==192
    rows=load(D/'test-outcomes.json.gz');sm=res['measures'];rc=len(rows);pairs=res['contrasts']
    names={'whole':'Целые узлы в порядке Dense-FT','parent':'Ядро и блоки по рангу родителя','fine':'Ядро и обученный fine','verbatim':'Verbatim, только выделение','verbatim_core':'Ядро и Verbatim 0,2','verbatim_fill':'Ядро, Verbatim и заполнение остатка','verbatim_recall_core':'Ядро и Verbatim 0,1'}
    lines=['# Сравнение с опубликованным VerbatimRAG ModernBERT v2','',
        'Проверено условное чтение истории ISETrace. Каждому методу доступны одни и те же 16 верхних исходных узлов Dense-FT, вопрос и лимит 2048 токенов E5. В выборке 192 различных траектории, по одному вопросу на каждую. Ревизия опубликованной модели — 6a967332, 150 млн параметров. Использованы авторский process, реальные строки и точные координаты. Fine обучен на ISETrace train. [Модель](https://huggingface.co/KRLabsOrg/verbatim-rag-modern-bert-v2/tree/6a967332efedfe5aca9b85b8310cc68d9ac6f881) · [протокол](PROTOCOL_RU.md) · [выборка](plan.json)','',
        '| Выдача | Полное покрытие | Среднее покрытие | Плотность | F1 | Средняя длина, токены | Пустые |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for arm,name in names.items():
        m=sm[arm];fs=sum(r['scores'][arm]['full'] for r in rows);empty=sum(r['scores'][arm]['empty'] for r in rows)
        lines.append(f"| {name} | {fs}/{rc} ({fmt(100*m['full'],1)}%) | {fmt(100*m['coverage'],1)}% | {fmt(100*m['density'],1)}% | {fmt(100*m['f1'],1)}% | {fmt(m['tokens'],1)} | {empty} |")
    p=pairs['fine-verbatim_core'];eq=equal['pairs_against_verbatim']['fine'];em=equal['measures']
    pval=p['mcnemar_two_sided'];pstr=f'{pval:.3g}'.replace('.',',')
    lines+=['',f"Первичный парный контраст fine минус Verbatim с общим ядром составил **{delta(p)}** по полному покрытию. Fine выиграл {p['wins']} пар и проиграл {p['losses']}, точное двустороннее p = {pstr}. Доверительные интервалы получены парным bootstrap по траекториям. При одинаковом горизонте потолок достижимого полного покрытия составляет {fmt(100*res['oracle']['full'],1)}%, если передать все доступные интервалы без ограничения длины. [Все метрики и интервалы](test-results.json) · [построчные результаты](test-outcomes.json.gz)",'',
        f"В дополнительной проверке каждому контролю выдан индивидуальный бюджет, равный фактической длине Verbatim с ядром. При этом fine достиг {fmt(100*em['fine']['full'],1)}%, Verbatim {fmt(100*em['verbatim_core']['full'],1)}%, целые узлы {fmt(100*em['whole']['full'],1)}%. Разность fine минус Verbatim {delta(eq)}. Средние фактические затраты составили {fmt(em['fine']['tokens'],1)}, {fmt(em['verbatim_core']['tokens'],1)} и {fmt(em['whole']['tokens'],1)} токенов соответственно. Точный предел расходов одинаков внутри каждой пары, её участники могут использовать разное число оставшихся токенов. [Протокол одинаковых индивидуальных лимитов](EQUAL_SPEND_RU.md) · [результаты](test-equal-spend-results.json)",'',
        f"Классификатор обработал {res['nodes']} пар «вопрос, узел» на двух потоках CPU. Наиболее длинная пара содержала {res['longest_pair']} токенов ModernBERT при окне 8192. Понадобилось свыше одного окна для {res['nodes_with_multiple_windows']} пар. При пороге 0,2 хотя бы один фрагмент выделен в {res['published_nonempty_nodes'][0]} узлах, при 0,1 — в {res['published_nonempty_nodes'][1]}. Для исходного порога измеренное время всех вызовов process на вопрос составило {fmt(res['query_seconds_default']['p50'])} с по медиане и {fmt(res['query_seconds_default']['p95'])} с по p95. Это время CPU в условиях соседних работ и одновременной тренировки на GPU. [Подписанные прогнозы и версии библиотек](test-seal.json)",'',
        'Оценки относятся к поиску точных символьных свидетельств при известных кандидатах. Порог, гранулярность фрагментов, защищённое ядро и степень заполнения доступного контекста влияют на покрытие. Здесь нет оценки действий решателя, распределение тестовых объектов отличается от выборки по всем вопросам, а fine имеет доменное обучение. Опубликованный Word-F1 отмечает частичное совпадение слов на другом корпусе. Эти условия определяют границы сравнения. [Статья](https://arxiv.org/abs/2605.21102) · [независимая проверка](verify.py)']
    lines+=['','При общем потолке fine расходует почти вдвое больше токенов, чем Verbatim с ядром. После выравнивания допустимых затрат на каждом вопросе оценка разности полного покрытия меняет знак, а доверительный интервал включает ноль. Такой результат указывает на вклад длины выдачи в исходное сравнение. Индивидуальный лимит задаёт сам экстрактор, поэтому это сравнение относится к распределению выбранных им длин. Для вывода об эквивалентности методов понадобилась бы отдельно заданная граница практически значимого различия.']
    if (D/'cost-results.json').exists():
        costs=load(D/'cost-results.json');assert costs['calls']==144 and costs['n']==24
        ms=costs['ms'];rat=costs['paired_latency_ratios']['verbatim_core/fine']
        lines+=['', '## Измеренная стоимость на общей панели','',
            f"На 24 одинаковых входах у трёх читателей проверены совпадения SHA текста с основными результатами. В 144 вызовах после прогрева медиана/p95 для целых узлов {fmt(ms['whole']['p50_ms'])}/{fmt(ms['whole']['p95_ms'])} мс, для fine {fmt(ms['fine']['p50_ms'])}/{fmt(ms['fine']['p95_ms'])} мс, для Verbatim с ядром {fmt(ms['verbatim_core']['p50_ms'])}/{fmt(ms['verbatim_core']['p95_ms'])} мс. На уровне запросов медианное отношение Verbatim/fine {fmt(rat['median'])}× (диапазон {fmt(rat['min'])}–{fmt(rat['max'])}×). В интервал включены вычисления читателя и повторная токенизация выдачи. Подготовка исходных кандидатов и загрузка модели выполнены заранее. [Протокол панели](COST_RU.md) · [исходные времена](cost-timings.json.gz) · [результаты](cost-results.json)"]
    (D/'REPORT_RU.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dest=D/'MANIFEST_SHA256.json'
    files={f.relative_to(D).as_posix():sha(f) for f in sorted(D.rglob('*')) if f.is_file() and f!=dest and '__pycache__' not in f.parts}
    dest.write_text(json.dumps({'count':len(files),'bytes':sum((D/n).stat().st_size for n in files),'files':files},indent=2,sort_keys=True)+'\n')
    assert all(sha(D/n)==v for n,v in files.items())
if __name__=='__main__':report()

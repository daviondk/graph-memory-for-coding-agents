"""Report all ranks tested using the same event grouping policy."""
from pathlib import Path
import json
from report import estimate,percent

HERE=Path(__file__).resolve().parent

def run():
    L=['# Может ли разнообразие событий улучшить полный контекст?',
       '', 'Каждое выбранное ранее свидетельство из того же события увеличивает штраф при выборе следующего фрагмента. Проверка включает обычный пропуск длинных узлов, переставленные event_id и предпочтение уже представленных событий. Для первичного сравнения использованы все 2 000 тестовых запросов и 1 207 траекторий. Бюджет каждой выдачи — 2 048 исходных токенов. [Предварительное описание](DIVERSITY_RU.md) · [Запечатанные параметры и входы](diversity-plan.json)',
       '', '| Ранги | Выбор | FS, % | Coverage, % | Событий в выдаче | Токенов | Покрытие пары при ≥2 эталонных событиях, % |',
       '|---|---|---:|---:|---:|---:|---:|']
    details=[]
    labels=dict(skip='Обычный skip',diverse='Штраф за повтор',sham='Штраф, переставленные ID',concentrate='Предпочтение повтора')
    for tag in ('dense','availability','hash64','full','degree_availability','degree_hash64'):
        f=HERE/f'diversity-{tag}-score.json'
        if not f.exists():
            continue
        z=json.loads(f.read_bytes())['panels']
        for m in labels:
            x=z['all']['methods'][m]
            p=z['multiple']['methods'][m]['pair']
            L.append(f"| {tag} | {labels[m]} | {percent(x['full_support'])} | {percent(x['coverage'])} | {x['events']:.2f} | {x['tokens']:.1f} | {percent(p)} |")
        p=z['all']['contrasts']['diverse minus skip']
        details.append(f"- {tag}. Изменение FS против skip {estimate(p['full_support'])} п.п., против переставленных ID {estimate(z['all']['contrasts']['diverse minus sham']['full_support'])} п.п. Изменение совместного покрытия среди многособытийных вопросов {estimate(z['multiple']['contrasts']['diverse minus skip']['pair'])} п.п. [Значения](diversity-{tag}-score.json)")
    L+=['','## Парные различия','','Каждый интервал рассчитан кластерным bootstrap по траекториям. Последнее сравнение использует 516 многособытийных вопросов.','',*details,'',
        'Разнообразие считается по фактическим событиям в отданном агенту контексте, включая неразмеченные. Совместное покрытие считает только эталонные события. Поэтому добавление разных источников может вытеснять высокоранговые релевантные фрагменты. Приоритеты и параметры совпадают для всех ранжировщиков. Влияние этой политики на написание кода или итоговые ответы агента в данном тесте не измерялось.',
        '', 'Для воспроизведения после подготовки входных рангов выполните `python -B diversify.py predict <панель>`, затем `python -B diversify.py score <панель>`, `python -B diversity_report.py` и `python -B verify_diversity.py`. Все отобранные списки фиксируются до загрузки эталона. [Код](diversify.py) · [Независимая проверка итогов](verify_diversity.py)']
    (HERE/'DIVERSITY_RESULTS_RU.md').write_text('\n'.join(L)+'\n',encoding='utf8')
if __name__=='__main__':
    run()

"""Report by original query mode and independently verify the grouped point estimates."""
from pathlib import Path
from statistics import mean
import hashlib
import gzip
import json
import math

HERE=Path(__file__).resolve().parent
ORDER=['direct_recall','linked_recall','multi_fact_recall']
def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def pct(n):return f'{100*n:.2f}'.replace('.',',')
def diff(record):
    a,b=record['ci95'];return f"{pct(record['estimate'])} [{pct(a)}; {pct(b)}]"
def main():
    z=read(HERE/'factor_hash64-results.json')
    L=['# Эффективность чтения графовой памяти по исходным классам ISETrace',
       '', 'В публичной разметке ISETrace 641 тестовый запрос Direct, 906 Linked и 453 Multi-fact. Эти классы описывают требуемую операцию чтения, тогда как число событий определяется физическими адресами эталонных символов. Из 516 вопросов, ссылающихся минимум на два события, 452 принадлежат классу Multi-fact, ещё 64 имеют метки Direct или Linked. Для одного Multi-fact достаточно символов из одного события.',
       '', '| Метка | Одно событие | Два события | Не менее трёх |',
       '|---|---:|---:|---:|']
    for m in ORDER:
        c=z['contingency'][m];L.append(f"| {m} | {c.get('1',0)} | {c.get('2',0)} | {c.get('3+',0)} |")
    L+=['', '## Full Support при 2 048 токенах',
        '', 'Сравнение на нативном prefix с общим пулом исходных фрагментов. Δ выражена в процентных пунктах. 95% интервалы парные с ресэмплированием целых траекторий. Одинаковые траектории повторно используются обеими группами при вычислении контраста разностей.',
        '', '| Сопоставление A − B | Метка | A, % | B, % | Разность FS, п.п. | Разность Coverage, п.п. |',
        '|---|---|---:|---:|---:|---:|']
    labels={'factor_hash64':'Ранг + степени − Dense-FT','hash64':'Hash64 R-GCN − точный seed',
        'full':'Полный R-GCN − точный seed','no_next_hash64':'Hash64, без next − все отношения','no_next_full':'Полный, без next − все отношения'}
    notes=[]
    for tag,name in labels.items():
        p=HERE/f'{tag}-results.json'
        if not p.exists():continue
        v=read(p);data=HERE/f'{tag}-data.json.gz'
        assert v['data']==h(data) and v['plan']==h(HERE/'plan.json')
        rows=read(data);assert len(rows)==len({r['q'] for r in rows})==2000
        for m in ORDER:
            group=[r for r in rows if r['mode']==m]
            assert sum(v['contingency'][m].values())==len(group)
            for k,t in v['groups'][m].items():
                assert math.isclose(mean(r['A'][k] for r in group),t['a'],abs_tol=1e-12)
                assert math.isclose(mean(r['B'][k] for r in group),t['b'],abs_tol=1e-12)
            fs=v['groups'][m]['full_support'];cov=v['groups'][m]['coverage']
            L.append(f"| {name} | {m} | {pct(fs['a'])} | {pct(fs['b'])} | {diff(fs)} | {diff(cov)} |")
        notes.append(f"- {name}. Разность выигрышей Multi-fact и Direct — {diff(v['multi_minus_direct']['full_support'])} п.п. [Поштучный расчёт]({tag}-results.json)")
    L+=['','## Различия между классами','',*notes]
    cp=HERE/'coverage-1024.json'
    if cp.exists():
        L+=['','## Меньший бюджет в исходной таблице 4','','| Метка | Dense-FT C@1024, % | Ранг + степени, % | Разность, п.п. |','|---|---:|---:|---:|']
        for m in ORDER:
            k=read(cp)['groups'][m]
            L.append(f"| {m} | {pct(k['methods']['dense'])} | {pct(k['methods']['degree'])} | {diff(k['degree_minus_dense'])} |")
    L+=['', 'В исходной статье при пяти семенах полный residual R-GCN получает 84,43/79,85/62,25% Full Support на Direct/Linked/Multi-fact, переобучаемый вариант без связи соседних чанков — 85,52/81,99/61,99%. В этой серии один seed. Оценки по классам описывают механизм на ранее использованных тестовых запросах. [Сопоставление с исходной таблицей 3](https://arxiv.org/html/2609.25913v3#S7.T3) · [Протокол](PROTOCOL_RU.md)',
        '', 'Восстановить по замороженным исходам: `python -B modes.py factor_hash64`, `python -B modes.py hash64`, `python -B modes.py no_next_hash64`, затем `python -B coverage.py` и `python -B report.py`. Если получены полные нативные ранги, добавляются `full` и `no_next_full`. Проверка сводок без исходного корпуса: `python -B report.py`.']
    (HERE/'REPORT_RU.md').write_text('\n'.join(L)+'\n',encoding='utf8')
    man={p.name:h(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    (HERE/'MANIFEST_SHA256.json').write_text(json.dumps(man,sort_keys=True,indent=2)+'\n',encoding='utf8')
    print(len(man),'files and every grouped estimate verified')
if __name__=='__main__': main()

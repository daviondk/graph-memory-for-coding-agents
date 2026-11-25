"""Summarize native retraining and independently verify its selected test outcomes."""
from pathlib import Path
import gzip
import hashlib
import json
import math
from statistics import mean

HERE=Path(__file__).resolve().parent
def h(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def pct(x):
    return f'{100*x:.2f}'.replace('.',',')
def effect(e):
    a,b=e['cluster_ci95'];return f"{pct(e['estimate'])} [{pct(a)}; {pct(b)}]"

def run():
    plan=read(HERE/'plan.json')
    assert h(HERE/'baseline.py')==plan['files']['adjacency_control/baseline.py']
    orig=plan['old'];new=plan['new']
    assert {k for k in orig if orig[k]!=new[k]}=={'ablation_name','enabled_provenance_relations'}
    assert set(orig['enabled_provenance_relations'])-set(new['enabled_provenance_relations'])=={'content.next'}
    lines=['# Нативный R-GCN с переобучением после удаления соседства чанков','',
        'В статье ISETrace удаление content.next с переобучением даёт опубликованное преимущество в 1,26 п.п. по Full Support@2048 относительно основной модели. Из основной строки 77,33% и округлённой разности следует ориентир около 78,59%. Ниже обе нативные модели обучаются с выбором лучшей эпохи по одним и тем же 500 dev и проверяются на всех 2 000 test одного seed. [Первоисточник](https://arxiv.org/html/2609.25913v3#S7.SS2) · [Зафиксированный протокол](PROTOCOL_RU.md)','',
        '| Обучающая панель | Полный граф, FS | Без content.next, FS | Разность FS, п.п. [95% ДИ] | Разность Coverage, п.п. [95% ДИ] | Ранг и степени против модели без content.next, Δ FS |',
        '|---|---:|---:|---:|---:|---:|']
    tracked=[]
    for tag in ('hash64','full'):
        p=HERE/tag;result=p/'matched-comparisons.json'
        if not result.exists():
            continue
        v=read(result);sg=read(p/'forecast-seal.json')
        predictions=sg.get('files',sg.get('forecasts'));assert predictions
        assert all(h(p/n)==digest for n,digest in predictions.items())
        assert h(p/'best.pt')==read(p/'checkpoint.json')['sha']
        assert h(p/'outcomes.json.gz')==v['outcomes'] and h(p/'train-pairs.json.gz')==read(p/'model-lock.json')['canonical_pairs']
        rows=[r for r in read(p/'outcomes.json.gz') if r.get('stage','test')=='test' and r['method']=='rgcn' and r['arm']=='prefix']
        assert len(rows)==len({r['q'] for r in rows})==2000 and sum(r['full_support'] for r in rows)==v['fs_hits']['no_next']
        x=v['comparisons']['trained_ablation_minus_native']['differences'];y=v['comparisons']['degree_minus_trained_ablation']['differences']
        m=v['fs_hits']
        assert math.isclose(x['full_support']['estimate'],(m['no_next']-m['native'])/2000,abs_tol=1e-12)
        assert math.isclose(y['full_support']['estimate'],(m['degree_hash64']-m['no_next'])/2000,abs_tol=1e-12)
        lines.append(f"| {tag} | {m['native']}/2 000 | {m['no_next']}/2 000 | {effect(x['full_support'])} | {effect(x['coverage'])} | {effect(y['full_support'])} |")
        lines+=['',f"[{tag}: парные различия]({tag}/matched-comparisons.json) · [Выбор checkpoint]({tag}/checkpoint.json) · [Ранги]({tag}/forecast-seal.json)",'']
        tracked.append(p)
    if not tracked:
        lines.append('Оба переобучения ожидают завершения. Результаты основной работы авторов указаны выше как внешний ориентир.')
    lines+=['','Малая hash64-панель содержит 101 обучающий вопрос. Dense-FT и структурный prior степеней используют данные исходного train c 3 894 вопросами. Сопоставление размерности графа и авторского отсева content.next становится точным при полном train, но один локальный seed не заменяет пяти seed статьи. Разбиение кандидатов, строгий prefix и бюджет совпадают.',
        '', 'Изначальная попытка проверить конфигурацию до обучения выявила несовпадение пути Windows с переносимым ключом манифеста. Исходная версия плана сохранена. Вторая фиксация использует POSIX-ключи и указывает ровно две заранее описанные метрики при парном сравнении. [Первоначальная фиксация](plan.initial.json) · [Действующая фиксация](plan.json)',
        '', 'Воссоздание из рабочей копии после подготовки исходных кешей: `python -B baseline.py fit hash64`, `python -B baseline.py rank hash64`, `python -B baseline.py score hash64`, затем `python -B report.py`. Для полной авторской панели используйте аргумент `full`. Все стадии переобучения повторно сверяют источник метода и идентичность разобранных пар, прогнозы фиксируются до scoring.']
    (HERE/'REPORT_RU.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    files={p.relative_to(HERE).as_posix():h(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    for d in tracked:
        files.update({p.relative_to(HERE).as_posix():h(p) for p in sorted(d.iterdir()) if p.is_file()})
    (HERE/'MANIFEST_SHA256.json').write_text(json.dumps(files,sort_keys=True,indent=2)+'\n',encoding='utf8')
    print('Native no-next statuses:', [p.name for p in tracked],len(files),'files verified')

if __name__=='__main__':
    run()

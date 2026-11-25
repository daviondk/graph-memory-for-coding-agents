"""Produce an immutable reduced-panel report while the full pre-registered run works."""
from pathlib import Path
import gzip
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def h(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    assert not (ROOT/'results.json').exists(),'Use seal.py for the complete full experiment.'
    panels=ROOT/'cpu_fallback'
    input_mans=[panels/'MANIFEST_SHA256.json',ROOT/'evidence_flow/MANIFEST_SHA256.json',ROOT/'adjacency_control/MANIFEST_SHA256.json',ROOT/'official_modes/MANIFEST_SHA256.json',ROOT/'serving_cost/MANIFEST_SHA256.json']
    nested={}
    for f in input_mans:
        data=read(f)
        assert 'REPORT_RU.md' in data and all(h(f.parent/k)==v for k,v in data.items())
        nested.update({(f.parent/k).relative_to(ROOT).as_posix():v for k,v in data.items()})
        nested[f.relative_to(ROOT).as_posix()]=h(f)
    x=read(panels/'hash64/results.json')['test']['metrics']
    top=read(panels/'hash64/topology-results.json')['metrics']
    f=read(ROOT/'cost-ft.json')
    before=read(ROOT/'gpu-resume-ft.json')
    assert f['missing']==0 and f['complete']==f['expected']==466074
    new='Сравнение с переобучаемым wo_chunk_adjacency зарегистрировано и поставлено на выполнение.'
    sub=ROOT/'adjacency_control/hash64/matched-comparisons.json'
    if sub.exists():
        assert 'adjacency_control/hash64/matched-comparisons.json' in nested
        a=read(sub)
        new=f"Переобучение wo_chunk_adjacency на малой панели даёт {a['fs_hits']['no_next']}/2 000 полных выдач (полный набор отношений {a['fs_hits']['native']}/2 000)."
    L=['# Нативный R-GCN и чтение свидетельств из графовой памяти','',
       f"Полный test ISETrace включает 2 000 запросов на 1 207 траекториях. Нативный residual R-GCN, обученный на 101 равновероятно отобранном по хешу train-вопросу внутри 64 траекторий, дал {x['rgcn/prefix']['hits']}/2 000 при prefix, точный seed {x['seed/prefix']['hits']}/2 000. Отбор равновероятен по траекториям, все вопросы выбранной траектории включаются вместе. При переходе от skip к приоритету аргумента или результата уже представленного вызова полнота снизилась с {x['rgcn/skip']['hits']}/2 000 до {x['rgcn/related']['hits']}/2 000. Другая модель обучена на 100 вопросах из числа уже доступных в момент перебоя входов. Обе панели прошли полные 15 эпох с выбором по 500 dev и отдельным SHA рангов перед открытием test-меток. [Обе панели и интервалы](cpu_fallback/REPORT_RU.md)",
       '', f"На hash64 при фиксированных весах исходные связи, соединения после перестановки адресатов и отсутствие сообщений дают соответственно {top['native']['hits']}, {top['random']['hits']} и {top['empty']['hits']} полных выдач из 2 000. {new} [Строгий контроль с переобучением](adjacency_control/REPORT_RU.md)",
       '', '## Чем объясняется рост совместного покрытия',
       '', 'Для train-only читателя, учитывающего роль и типизированные степени графа, вероятность полного извлечения случайного эталонного события увеличилась с 69,43% до 75,76%. Вероятность извлечения двух событий вместе выросла с 51,65% до 61,08%. Расчёт выполнен на 516 запросах из 481 траектории. Дополнительное изменение ковариации двух событий равно +0,24 п.п. [−1,80;2,29]. Малые нативные R-GCN показывают существенно меньший прирост. [Полные исходы, абляции и формулы](evidence_flow/REPORT_RU.md)',
       '', 'Принудительный штраф за повторное представление одного события увеличивает число разных событий в выдаче Dense-FT, одновременно снижая Full Support на 1,20 п.п. [−1,96;−0,45]. Проверены перестановка идентификаторов внутри классов длины и обратный приоритет. [Политики, стоимость и переносы](evidence_flow/DIVERSITY_RESULTS_RU.md)',
       '', '## Статус полноразмерного сопоставления',
       '', f"Источник FP32-эмбеддингов полного E5-FT имеет {f['complete']:,} подтверждённых ключей, отсутствующих 0. После восстановления CUDA вычислены {before['new']:,} дополнительных векторов за {before['seconds']:.1f} с. Базовый E5 используется для авторского выбора сложных отрицательных примеров. Этот снимок содержит завершённые прогнозы двух уменьшенных train-панелей и входы полного расчёта. Основная строка статьи составляет 77,33 ± 0,53% Full Support@2048 по пяти семенам, наиболее сильная из опубликованных структурных абляций даёт ещё 1,26 п.п. Полный локальный seed 13 и пятисеменное сравнение остаются отдельными этапами. [Проверка полноты FT](cost-ft.json) · [Процедура восстановления](RECOVERY_RU.md) · [Статья, §7.2](https://arxiv.org/html/2609.25913v3#S7.SS2)",
       '', 'Проверка данного снимка на Python 3.11+ без исходного корпуса: `python -B verify_checkpoint.py`. У каждого включённого вложенного эксперимента сохранены файлы для повторного подсчёта. Полная процедура обучения и бюджетный контроль описаны в отдельном протоколе. [Воспроизведение](REPRODUCE_RU.md)']
    L.insert(L.index('## Статус полноразмерного сопоставления'), 'По исходным классам ISETrace выигрыш Full Support у rank + degree относительно Dense-FT составил +2,50 п.п. на Direct, +4,86 на Linked и +12,58 на Multi-fact. Разность эффектов Multi-fact и Direct равна +10,09 п.п. [5,86;14,37]. [По классам и двум бюджетам](official_modes/REPORT_RU.md)')
    L.insert(L.index('## Статус полноразмерного сопоставления'), '')
    L[2]=L[2].replace('101 равновероятно отобранном по хешу train-вопросу внутри 64 траекторий','101 train-вопросе из 64 траекторий, выбранных по SHA-256')
    L.extend(['', 'На 96 запросах оба читателя получают один вектор cosine. Медианное время тёплого CPU-ранжирования и формирования prefix составило 0,062 мс у ранга со степенями и 7,538 мс у малого нативного R-GCN. Интервал начинается после получения результата Dense-FT. [Раздельный учёт обслуживания и памяти](serving_cost/REPORT_RU.md)'])
    (ROOT/'REPORT_RU.md').write_text('\n'.join(L)+'\n',encoding='utf8')
    exclude={'MANIFEST_SHA256.json','MANIFEST_FULL_SHA256.json'}
    included={p.name:h(p) for p in sorted(ROOT.iterdir()) if p.is_file() and p.suffix in {'.py','.md','.ps1'} and p.name not in exclude}
    inputs=['REPORT_RU.md','protocol-lock.json','fit-lock.json','fit-lock.initial.json','native-smoke.json','vectors-plan.json','source-cache-audit.json','cost-dev.json','cost-ft.json',
        'gpu-outage.json','outage-coverage.json','outage-train-availability.json.gz','cpu-bench.json','dev500-pu-dense-lock.json','dev500-pu-dense-ranks.json.gz','dev500-calibration.json',
        'candidate-call-map.json.gz','candidate-map-receipt.json','gpu-resume-ft.json']
    inputs.extend(x for x in ['gpu-resume-base.json','cost-base.json','direct-embedding-audit.json','pair-inventory.json','train-pairs.json.gz'] if (ROOT/x).exists())
    for path in inputs:
        included[path]=h(ROOT/path)
    for f in (ROOT/'topology').iterdir():
        if f.is_file() and (f.suffix in {'.py','.md','.ps1'} or f.name in {'protocol-lock.json','edge-invariants.json','strata-plan.json','topologies.json.gz'}):
            included[f.relative_to(ROOT).as_posix()]=h(f)
    included.update(nested)
    target=ROOT/'MANIFEST_SHA256.json'
    target.write_text(json.dumps(included,sort_keys=True,indent=2)+'\n',encoding='utf8')
    print('Reduced checkpoint:',len(included),h(target))

if __name__=='__main__':
    main()

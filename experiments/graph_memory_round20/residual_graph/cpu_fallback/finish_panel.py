"""Publish a completed panel as an individually verifiable archive."""
from pathlib import Path
import hashlib,json,shutil,sys
from verify_panel import verify,v,HERE,ROOT
def fmt(f):return ('%.2f'%f).replace('.',',')
def delta(c):
    d=c['differences']['full_support'];a,b=d['cluster_ci95']
    return f"{fmt(100*d['estimate'])} п.п. [{fmt(100*a)}; {fmt(100*b)}]"
def seal(name):
    verify(name);sub=HERE/name;res=v.get(sub/'results.json');cohort=v.get(HERE/'cohorts.json')[name];ck=v.get(sub/'checkpoint.json');enc=v.get(sub/'cpu-encoding.json')
    other='62 траектории с максимум двумя отсутствовавшими FT-строками на момент прерывания CUDA' if name=='availability' else '64 траектории по SHA ID из всех 2 410 оригинальных train-траекторий, независимо от текущего кэша'
    L=['# Нативный R-GCN на уменьшенной train-панели','',
    f"Панель {name}: {other}. Использованы {len(cohort['q'])} train-вопросов. Все положительные, отрицательные, графовые признаки, модель и метод выбора dev-эпохи — из нативного публичного алгоритма. Размер обучающей панели отличается от полной авторской конфигурации 3894 train. Исходное сопоставление с обученным standalone Dense-FT описано в соседней серии. Отсутствующие эмбеддинги дорассчитаны на CPU FP32.",'',
    f"Формирование {len(v.get(sub/'train-pairs.json.gz'))} размеченных пар использовало 2 easy, 2 BM25, 1 исходную E5 и 1 графовую выборку на положительный (доступность зависит от траектории). Проведено {ck['steps']} обновлений за 15 эпох. Штатная валидация на 500 dev сохранила эпоху {ck['best_epoch']}, node Recall@5 {fmt(100*ck['metric'])}%. Модель в best.pt, SHA в checkpoint.json.",'',
    '| Страта | Ранжировщик | Правило чтения | Полное покрытие, n/N (%) | Coverage, % | F1, % | Токенов |','|---|---|---|---:|---:|---:|---:|']
    for st in ('test','dev'):
        for m in ('rgcn','seed'):
            for arm in ('prefix','skip','related'):
                s=res[st]['metrics'][m+'/'+arm]
                L.append(f"| {st} | {m} | {arm} | {s['hits']}/{s['n']} ({fmt(100*s['full_support'])}) | {fmt(100*s['coverage'])} | {fmt(100*s['f1'])} | {fmt(s['tokens'])} |")
    D=res['test']['contrasts'];L+=['',
    f"На 2 000 test разность R-GCN prefix и точного seed prefix — **{delta(D['rgcn/prefix - seed/prefix'])}**; related против skip после R-GCN — **{delta(D['rgcn/related - rgcn/skip'])}**. Доверительные интервалы 95%, парный кластерный бутстреп по траекториям, 10 000 повторов. Оценено извлечение полного набора координат. [Результаты](results.json) · [Поштучные метрики](outcomes.json.gz)",'',
    f"Чистое время fit с валидацией {fmt(ck['fit_seconds']/60)} мин, подготовка векторов и пар {fmt(ck['preparation_seconds']/60)} мин. Последний завершённый этап кодирования на CPU добавил {enc['base']['new']} базовых и {enc['ft']['new']} FT-векторов. Для hash64 этот счётчик относится только к продолжению после перезапуска. До него были сохранены ещё 4 192 базовых и 2 384 FT-вектора этой панели. Итого 6 281 базовый и 2 384 FT для hash64. Первоначальные времена и число строк восстановлены по логам, полный token-счётчик прерванного этапа отсутствует. В обоих исходных тестовых вариантах предъявлены все кандидаты и одинаковые бюджетные правила. Один seed и малый обучающий набор ограничивают интерпретацию. [Запечатанные прогнозы](forecast-seal.json) · [Отбор панели](../cohorts.json) · [Протокол](../PROTOCOL_RU.md)"]
    (sub/'REPORT_RU.md').write_text('\n'.join(L)+'\n',encoding='utf8')
    manifest={f.name:v.sha(f) for f in sorted(sub.iterdir()) if f.is_file() and f.name!='MANIFEST_SHA256.json'}
    p=sub/'MANIFEST_SHA256.json';p.write_bytes((json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode());print(name,len(manifest),v.sha(p))
if __name__=='__main__':seal(sys.argv[1])


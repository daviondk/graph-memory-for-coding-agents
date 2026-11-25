"""Render costs and independently recalculate all timing point estimates."""
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
import gzip
import hashlib
import json
import math

HERE=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(n,k=3):return f'{n:.{k}f}'.replace('.',',')
def q95(xs):
    x=sorted(xs);pos=.95*(len(x)-1);i=math.floor(pos)
    return x[i]+(pos-i)*(x[math.ceil(pos)]-x[i])
def main():
    plan=read(HERE/'plan.json')
    assert plan['code']==h(HERE/'bench.py') and plan['protocol']==h(HERE/'PROTOCOL_RU.md')
    L=['# Стоимость чтения после общего Dense-FT на CPU','',
       'Две политики получают один фактический FP32 cosine для каждого кандидата из подготовленного нативного батча. Считали время до одного и того же типа результата — полный порядок ID кандидатов и набор ID, помещающийся в 2 048 токенов strict prefix. В каждый замер входит сортировка и упаковка. Для R-GCN до этой точки уже собран батч размером один. Для rank + degree уже вычислен скаляр приоритета на каждый кандидат. Локальная машина обслуживала фоновые задачи; порядок двух путей чередовался по вопросу и повтору. [Протокол](PROTOCOL_RU.md)',
       '', '| Обучение R-GCN | Метод | p50, мс | p95, мс | Среднее, мс |',
       '|---|---|---:|---:|---:|']
    notes=[]
    for tag in ('hash64','full'):
        p=HERE/f'{tag}-cost.json'
        if not p.exists():continue
        r=read(p);rp=HERE/f'{tag}-measurements.json.gz';m=read(rp)
        assert r['measurements']==h(rp) and r['plan']==h(HERE/'plan.json')
        assert set(m['queries'])==set(plan['q']) and r['threads']==r['interop_threads']==r['batch']==1
        grouped=defaultdict(list)
        for row in m['times']:grouped[row['q']].append(row)
        assert len(m['times'])==96*8
        assert all(len(v)==8 and sum(x['first']=='degree' for x in v)==4 for v in grouped.values())
        med={}
        for name in ('degree','native'):
            vals=[median(row[name+'_ns'] for row in grouped[q]) for q in plan['q']]
            med[name]=vals
            cost=r['online'][name+'_ns']
            assert all(math.isclose(x,y,rel_tol=1e-11) for x,y in [(mean(vals),cost['mean']),(median(vals),cost['p50']),(q95(vals),cost['p95'])])
            L.append(f"| {tag} | {'Ранг и степени' if name=='degree' else 'Нативный R-GCN'} | {fmt(cost['p50']/1e6)} | {fmt(cost['p95']/1e6)} | {fmt(cost['mean']/1e6)} |")
        ratio=mean(med['degree'])/mean(med['native'])
        assert math.isclose(ratio,r['online']['ratio_mean'])
        ci=r['online']['ratio_ci95']
        notes.extend(['',f"**{tag}.** Отношение средних задержек rank + degree к R-GCN — {fmt(ratio,5)} [95% ДИ {fmt(ci[0],5)}; {fmt(ci[1],5)}]. Обратное отношение равно {fmt(1/ratio,1)}. Сначала бралась медиана восьми измерений на каждый запрос, затем одинаковый вес получал каждый запрос.",
           '',f"На {r['trajectories']} уникальных траекториях разовая компиляция структурного приоритета заняла {fmt(r['prior_build_ns']/1e6,2)} мс суммарно. Привязка этого массива к порядку кандидатов всех 96 запросов заняла {fmt(r['alignment_ns']/1e6,2)} мс. Материализация нативных числовых тензоров для этих запросов заняла {fmt(r['native_tensorize_ns']/1e6,2)} мс, отдельная сборка батчей — {fmt(r['native_collate_ns']/1e6,2)} мс. Эти объёмы относятся к разным стадиям и числу обращений. Они не входят в предшествующую таблицу.",
           '',f"Исходные сжатые проекции на диске занимают {r['source_graph_gzip_bytes']:,} байт. FP32-входы узлов имеют {r['common_graph_passage_embedding_bytes_before_intertrajectory_dedup']:,} числовых байт до межтраекторной дедупликации, FP32-векторы запросов — {r['common_query_embedding_bytes']:,}. Компактный массив одного float64 приоритета на PU занимает {r['degree_store']['float64_scalar_bytes']:,} байт. Если хранить восемь int32 вместо скаляра, массив занимает {r['degree_store']['eight_int32_bytes']:,} байт. Эти величины исключают ID и служебные накладные расходы БД. Коэффициенты ранга и степеней имеют {r['model']['degree_and_rank_weight_bytes']} байта численного payload. Сериализованный обученный checkpoint R-GCN имеет {r['model']['rgcn_checkpoint_bytes']:,} байт, включая метаданные. Масса E5 общая и не входит в оба числа.",
           '',f"Один и тот же cosine-вектор использовался на двух путях для каждого из 96 запросов. Внешний автономный Dense-FT полностью совпал с ранжированием по этим нативным числам в {r['match']['dense_order_equal']} случаях. Проверка prefix с ранее запечатанными независимыми рангами даёт {r['match']['degree_prefix_equal']}/96 у степеней и {r['match']['native_prefix_equal']}/96 у R-GCN. Максимальное отклонение нативных оценок от пакетной выгрузки — {r['worst_native_score_error']:.3g}. [Сводка]({tag}-cost.json) · [Поштучные измерения]({tag}-measurements.json.gz)"])
    L+=notes+['', 'Время интерпретации запроса, кодирования E5, доступа к БД и генерации ответа в онлайновый интервал не входит. Числа описывают только добавочный локальный этап после получения семантического сигнала; влияние на полную задержку зависит от доли этого этапа. Для воспроизведения на тех же данных: `python -B bench.py hash64` или `python -B bench.py full`, затем `python -B report.py`. Последняя команда отдельно проверяет арифметику поштучных измерений готового пакета средствами стандартной библиотеки.']
    (HERE/'REPORT_RU.md').write_text('\n'.join(L)+'\n',encoding='utf8')
    files={p.name:h(p) for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    (HERE/'MANIFEST_SHA256.json').write_text(json.dumps(files,sort_keys=True,indent=2)+'\n',encoding='utf8')
    print('Paired stage costs and data files verified:',len(files))

if __name__=='__main__':main()

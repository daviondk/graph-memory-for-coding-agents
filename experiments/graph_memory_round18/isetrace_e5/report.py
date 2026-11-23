"""Build a short Russian report from verified measurements."""
import gzip,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def load(n):
    p=ROOT/n
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def f(v,n=2):return format(v,f'.{n}f').replace('.',',')
def p(v):return f(v*100)
def ci(x):return '['+p(x[0])+'; '+p(x[1])+']'
def write():
    res=load('results.json');ma=res['groups']['main'];cost=load('cost-fp32.json');cpu=load('cpu-check.json');grid=load('grid-results.json');pl=load('placebo-results.json');tk=load('token-cost.json')
    b=load('throughput.json');iv=load('inventory.json');cal=res['published_prefix'];n=res['n_query']
    txt=['# Упаковка графовой памяти при замороженном E5','',
         f"Полный официальный test split ISETrace v7 включает {n} запросов по {res['n_trajectories']} траекториям. Проверено, помогает ли при сохранении исходного ранжирования добрать из памяти вторую сторону уже выбранного инструментального вызова. Полнота поддержки (FS) означает, что в окно попали все эталонные символы запроса. Coverage измеряет долю эталонных символов, density — их долю в переданном материале. F1 усредняется по запросам.",
         '',f"В таблице 1 у Wang et al. frozen PU Dense достигает 50,50% FS и 58,20% Coverage при B=2048. Наша базовая реализация дала **{p(ma['prefix']['full_support'])}%** и **{p(ma['prefix']['coverage'])}%**. Одинаковые веса и SHA версии авторского кода, одни и те же 2 000 ID, пять вариантов используют одну и ту же сохранённую перестановку кандидатов. [Wang et al., таблица 1](https://arxiv.org/html/2609.25913v3#S6.T1)",
         '', '| Упаковка | FS, запросы | FS, % | Coverage, % | Density, % | F1, % | Токенов | Блоков |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for arm in ('prefix','clip','skip','value','related'):
        v=ma[arm];txt.append(f"| {arm} | {v['fs_hits']}/{n} | {p(v['full_support'])} | {p(v['coverage'])} | {p(v['density'])} | {p(v['f1'])} | {f(v['tokens'],1)} | {f(v['nodes'],1)} |")
    txt+=['','Prefix останавливается у первого слишком длинного чанка. Clip берёт доступную часть следующего чанка до точной границы исходного токена. Skip пропускает неподходящие блоки и продолжает в порядке оценки. Value упорядочивает оставшиеся целые блоки по score/√tokens. Related приоритетно рассматривает противоположную сторону того же вызова среди оставшихся блоков. После неё продолжает в исходном E5-порядке.','',
          '| Парный контраст | Δ FS, п.п. | 95% ДИ, п.п. | Выиграл / проиграл / поровну | Δ Coverage, п.п. | Δ токенов |','|---|---:|---:|---:|---:|---:|']
    for a in ['related-prefix','related-skip','related-value','related-clip','prefix-bm25_prefix','related-bm25_related']:
        v=res['paired']['main/'+a];d=v['differences']
        txt.append(f"| {a} | {p(d['full_support']['estimate'])} | {ci(d['full_support']['cluster_ci95'])} | {v['fs_wins']} / {v['fs_losses']} / {v['fs_ties']} | {p(d['coverage']['estimate'])} | {f(d['tokens']['estimate'])} |")
    txt+=['','Δ определяется порядком строк, для последних двух положительное значение означает преимущество E5 над одноимённой PU-BM25. Доверительные интервалы — парный bootstrap целых траекторий, 10 000 повторов, seed 13. Сравнения используют тестовую выборку, на которой команда ранее изучала BM25. Учёт 16 перестановок ниже ведётся внутри случая.','',
          '## Контроль идентичности ребра','',
          '| Стратификация при перестановке | Истинное FS, % | Среднее FS при перестановке, % | Δ, п.п. | 95% ДИ, п.п. | Изменился набор, % запросов × seed | Δ токенов |','|---|---:|---:|---:|---:|---:|---:|']
    for a,v in pl.items():
        x=v['true_mean'];y=v['shuffled_mean']
        txt.append(f"| {a} | {p(x['full_support'])} | {p(y['full_support'])} | {p(x['full_support']-y['full_support'])} | {ci(v['diff_fs_boot95'])} | {p(v['changed_fraction'])} | {f(x['tokens']-y['tokens'])} |")
    txt+=['','При strict совпадают тип операции, число событий и число чанков по каждой стороне, при event_degree совпадают тип операции и числа событий. Обе политики сохраняют стоимость каждого исходного узла. У singleton-вызовов идентичность связи остаётся прежней. Доля изменившихся наборов показывает, скольким запросам тест действительно поменял содержимое.','',
          '## Бюджетная кривая','',
          '| Лимит | prefix FS, % | clip | skip FS, % | value FS, % | related FS, % | related Coverage, % |','|---|---:|---:|---:|---:|---:|---:|']
    G=grid['policies']
    for limit in (256,512,1024,2048,4096,8192):
        a={k:v['by_budget'][str(limit)] for k,v in G.items()}
        clip=p(ma['clip']['full_support']) if limit==2048 else '—'
        txt.append(f"| {limit} | {p(a['prefix']['full_support'])} | {clip} | {p(a['skip']['full_support'])} | {p(a['value']['full_support'])} | {p(a['related']['full_support'])} | {p(a['related']['coverage'])} |")
    txt+=['','| Упаковка | FS Budget-AUC, % | Coverage Budget-AUC, % |','|---|---:|---:|']
    for a,v in G.items():txt.append(f"| {a} | {p(v['auc']['full_support'])} | {p(v['auc']['coverage'])} |")
    d=G['related']['auc']['full_support']-G['skip']['auc']['full_support'];txt+=['',
           f"Площадь рассчитана нативной функцией нормированных трапеций по log₂ B. Для related против skip разность FS-AUC {p(d)} п.п., 95% ДИ {ci(grid['related_minus_reference_auc_ci95']['skip']['full_support'])}. Все шесть лимитов соответствуют статье.",'',
           '## Вычислительные условия','',
           f"Модель intfloat/e5-base-v2, FP32, TF32 выключен, PyTorch {b['torch']}, RTX 3090. Замер 512 реальных строк дал {f(b['samples']['fp32']['strings_per_second'],1)} строк/с. Полное кодирование {iv['unique_prefixed_strings']} уникальных строк заняло {f(cost['seconds']/60,1)} мин. Вход содержал {tk['actual_unpadded_input_tokens']:,} токенов до padding. Пик CUDA-тензоров по PyTorch {f(cost['peak_allocated_gpu_bytes']/2**30)} GiB. Опубликованы хеши весов, ранги с точными смещениями и все поштучные исходы. Чанки отбирались из {iv['candidate_occurrences']} вхождений по {iv['n_trajectories']} траекториям. Затраты читателя и длительность построения всего индекса модели не эквивалентны лимиту предъявляемых исходных токенов.",
           '',f"Из более раннего CPU-прогона пересеклись {cpu['overlap']} запросов. Согласие top-1 {cpu['equal_top1']}/{cpu['overlap']}, первых пяти в исходном порядке {cpu['equal_top5_in_order']}/{cpu['overlap']}, полного порядка {cpu['equal_complete_ranking']}/{cpu['overlap']}. Макс. |разность score| {cpu['max_abs_score_difference']}.",
           '',"В работе Wang et al. обученный residual R-GCN с пятью seed достигает 77,33% FS@2048. Результат этой серии описывает frozen retrieval и полноту входной памяти. Для общего рекорда и эффекта на итоговом ответе необходимы сравнение с обученным решением и отдельный downstream-тест. [Статья и условия обучения](https://arxiv.org/html/2609.25913v3#S6.T1)"]
    bounds=load('calibration-bounds.json');outside=load('sensitivity.json')['outside_R17_trajectories']
    txt+=['','## Границы воспроизводимости и перенос эффекта','',
          f"Исключение 128 траекторий, назначенных в R17, оставляет {outside['n']} запросов. Related достигает {p(outside['arms']['related']['full_support'])}% FS и опережает skip на {p(outside['related_minus']['skip']['delta'])} п.п., 95% ДИ {ci(outside['related_minus']['skip']['cluster_ci'])}. Отдельный файл sensitivity.json содержит все три авторских типа вопросов.",
          '',"Калибровка отличается от статьи на один запрос FS и примерно 0,10 п.п. Coverage. Среднее число PU на запрос 124,5445 точно округляется до опубликованных 124,54. После получения результатов проверили возможные перестановки кандидатов в группе почти равных оценок у границы префикса. При соседнем разрыве ≤10⁻⁶ даже консервативная нижняя и верхняя границы FS/Coverage совпадают с нашим prefix. Следовательно, объяснение только такими перестановками не соответствует наблюдениям. При 10⁻⁴ диапазоны допускают опубликованные значения, но фактическая причина остаётся неизвестной без оригинальных поштучных рангов. Авторская статья сообщает показатели с двумя знаками, протокол сравнения здесь использует одну общую локальную перестановку внутри запроса."]
    (ROOT/'REPORT_RU.md').write_bytes(('\n'.join(txt)+'\n').encode())
if __name__=='__main__':write()

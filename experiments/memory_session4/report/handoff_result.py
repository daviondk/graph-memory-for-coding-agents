from layout import *

def value(x):
    return n(x) if x==int(x) else dec(x,1)

def result_page():
    allresults=J('handoff/results.json')
    main=allresults['reader']['clean']
    shuffle=J('handoff/shuffle/results.json')
    strict=J('handoff/strict/results.json')
    assert main['n']==shuffle['n']==strict['n']==96
    m=main['metrics'];cost=main['costs']
    page('Выбор уже созданного исправления','Что выбрал настоящий читатель','У 70 задач оба patch прошли тесты, у 14 оба не прошли. Только 12 из 96 пар различаются по официальному исходу.')
    rows=[]
    for name,key in [('Без записки','empty'),('Последние проверки','latest'),('Свидетельство и свежесть','witness')]:
        rows.append([name,value(2*m[key]['success_sum']),perc(m[key]['mean']),str(cost[key]['order_disagreement'])])
    rows.append(['Переставленная записка',value(2*shuffle['metrics']['success_sum']),perc(shuffle['metrics']['mean']),str(shuffle['order_disagreement'])])
    rows.append(['Strict с частичным CPU',value(2*strict['metrics']['success_sum']),perc(strict['metrics']['mean']),str(strict['order_disagreement'])])
    for name,key in [('Всегда Claude','claude'),('Всегда Gemini','gemini'),('Source prior по другим repository','heldout_repository_prior'),('Простое правило последнего теста','last'),('Лучший patch пары по эталону','oracle')]:
        rows.append([name,value(2*m[key]['success_sum']),perc(m[key]['mean']),'—'])
    tbl(['Правило','Успехов\nиз 192','Доля','Смена источника\nиз 96 задач'],rows,[7.0,2.6,2.7,4.8])
    d=main['contrasts']['witness_minus_empty'];lo,hi=d['repository_cluster_ci95']
    p('Свидетельство меняет средний успех на '+pp(d['difference'],2)+' п.п., 95% интервал ['+pp(lo,2)+', '+pp(hi,2)+']. На уровне задач '+str(d['wins'])+' выигрышей и '+str(d['losses'])+' потерь. Два порядка усредняются внутри задачи, CI кластеризуется по repository. 192 предъявления зависимы.')
    q=shuffle['correct_minus_permuted'];ql,qh=q['repository_cluster_ci95']
    p('Корректная записка относительно переставленной даёт '+pp(q['difference'],2)+' п.п., интервал ['+pp(ql,2)+', '+pp(qh,2)+']. Этот контроль проверяет связь записи с задачей. Он добавлен до исходов, все контрасты этого reader остаются exploratory.')
    g=cost['gate_disagreement'];gd=main['contrasts']['gate_disagreement_minus_gate_equal_count_hash']
    p('Чтение по смене источника сработало на '+str(g['gated_issues'])+' задачах и дало '+value(2*m['gate_disagreement']['success_sum'])+' успехов из 192. Равный hash-gate дал '+value(2*m['gate_equal_count_hash']['success_sum'])+'. Цена '+n(g['total_tokens'])+' номинальных токенов против '+n(cost['witness']['nominal_total_tokens'])+' у always-read. Переключения включают одинаковые patch, поэтому сырая метка источника преувеличивает содержательную неустойчивость.')
    p('Posthoc проверка нашла 10 одинаковых patch без расхождения их labels. На 86 различных парах источник меняется в 67. Модель предпочитает позицию B в 173 из 192 no-memory ответов и 151 witness-ответе. Gate только по различным patch всё ещё даёт 152 успеха при 402 580 токенах.')
    p('Strict включает 183 GPU и 9 CPU вызовов после сбоя CUDA. На 87 задачах с обоими GPU-предъявлениями strict даёт 136 успехов из 174 против 135 у witness, разница +0,57 п.п. [−0,81, +4,29]. Невалидных ответов модели во всех этих вариантах нет.')


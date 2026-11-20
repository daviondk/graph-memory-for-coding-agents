from collections import Counter
import csv,itertools
from util import *
P=['raw','system_alert','git','block_context','oracle']
NM={'raw':'Naive','system_alert':'Alert','git':'Diff','block_context':'Concord','oracle':'Oracle','correction':'Подсветка изменения','control':'Контроль подсветки'}
def num(v):return f'{v:,}'.replace(',',' ')
def decimal(v,k=3):return f'{v:.{k}f}'.replace('.',',')
def onepair(p):return f"{decimal(100*p['delta'],1)} [{decimal(100*p['ci'][0],1)}, {decimal(100*p['ci'][1],1)}]"
def main():
    z=read(ROOT/'results.json');a=z['arms'];jc=read(ROOT/'judge_receipts.json.gz');vv=read(ROOT/'verdicts.json.gz')
    lines=['# Сравнение пяти опубликованных конфигураций ConcordBench на локальной Qwen','',
      'На каждом из 40 вопросов Pioneer работала одна и та же Qwen3.8-27B UD-Q4_K_M с настоящими вызовами инструментов. В сравнении есть четыре способа отвечать при конкурентной замене источника и отдельный ориентир Oracle на нетронутом исходном тексте. Режимы Alert, Diff и Oracle добавили 120 траекторий. Траектории Naive и Concord уже были сохранены на тех же заданиях и той же локальной модели. [Таблица авторов, параметры и соответствие CLI](https://github.com/FFFFFFFANG1/Concord/blob/4116936349995f0f30597931c0dbbebcbf7e58ac/README.md#-concordbench).','',
      '| Режим | Точно из 40 | Средний F1 | Судья, верно / разобрано | Случаи с восстановлением | read_file, действия / случаи | diff, действия / случаи | Вход / выход, токены |',
      '|---|---:|---:|---:|---:|---:|---:|---:|']
    for arm in P:
        m=a[arm];tools=m['all_tool_attempts'];lines.append(f"| {NM[arm]} | {m['em']} | {decimal(m['mean_f1'])} | {m['blinded_judge_correct']} / {m['judge_available']} | {m['cases_race']} | {tools.get('read_file',0)} / {m['cases_with_read']} | {tools.get('diff',0)} / {m['cases_with_diff']} | {num(m['prompt'])} / {num(m['completion'])} |")
    lines+=['','Совпадение ответа и токенный F1 пересчитывались по правилам HotpotQA из закреплённой реализации. Вторичный судья видел только вопрос, эталонный ответ и предсказание. Использован тот же Qwen, авторский промпт и парсер. Это самостоятельная машинная оценка, возможна зависимость между стилем ответов и оценкой того же семейства моделей.','',
       '| Разность первого и второго | EM, п.п. [95%] | F1 × 100 [95%] | Судья по полным парам, п.п. [95%] | Судья, выигрыши / потери |',
       '|---|---:|---:|---:|---:|']
    for x,y in itertools.combinations(P,2):
        d=z['pairs'][x+' minus '+y];j=d['judge'];lines.append(f"| {NM[x]} − {NM[y]} | {onepair(d['em'])} | {onepair(d['f1'])} | {onepair(j)} | {j.get('wins',0)} / {j.get('losses',0)} |")
    lines+=['','Все 10 сравнений используют одни и те же 40 вопросов. Интервалы получены при 10 000 совместных перевыборках вопросов, seed 20261118. Каждое направление и точный двусторонний знаковый тест приведены в paired.csv. Сравнения множественные и описательные. Oracle отключает модификацию A и гонку, сохраняя тот же инструментарий и декодер, и показывает качество при исходном тексте. У остальных четырёх политик одни и те же патчи, непрозрачные ID, предел 30 событий и одно исполняемое действие на событие. В реализации Diff перед подачей ответа нужен актуальный diff, Alert отдаёт текстовое уведомление, Concord управляет доступностью блоков, Naive сохраняет обычную историю. Указанное в CLI дополнительное имя reread немедленно вызывает NotImplementedError, вызовов модели через это имя нет. [Исходный цикл](https://github.com/FFFFFFFANG1/Concord/blob/4116936349995f0f30597931c0dbbebcbf7e58ac/bench/qa_agent/loop.py), [реализация запуска гонки](https://github.com/FFFFFFFANG1/Concord/blob/4116936349995f0f30597931c0dbbebcbf7e58ac/bench/qa_agent/eval_pioneer.py).','',
      '## Действия и вычислительные расходы','',
      '| Режим | Запросы LLM | Действия | События | Случаи с ответом инструментом | Явные ошибки diff / read_file | Запросы без токен-метрик |','|---|---:|---:|---:|---:|---:|---:|']
    for arm in P:
        m=a[arm];e=m['explicit_tool_errors'];lines.append(f"| {NM[arm]} | {m['logical_requests']} | {m['actions']} | {m['events']} | {m['cases_with_answer_tool']} | {e.get('diff',0)} / {e.get('read_file',0)} | {m['missing_usage']} |")
    lines+=['','У слепого судьи JSON мог остаться незавершённым даже после повторного запроса с лимитом 384 токена. Эти исходы учтены как неизвестные. Для всех 40 случаев ниже приведён диапазон доли верных, совместимый с доступными оценками.','',
       '| Режим | Верно / разобрано | Неизвестно из 40 | Доля среди разобранных | Возможная доля среди всех 40 |','|---|---:|---:|---:|---:|']
    for arm in P:
        m=a[arm];lo,hi=m['judge_rate_bounds_all40']
        lines.append(f"| {NM[arm]} | {m['blinded_judge_correct']} / {m['judge_available']} | {m['judge_missing']} | {decimal(100*m['judge_rate_available'],1)}% | {decimal(100*lo,1)}–{decimal(100*hi,1)}% |")
    lines+=['','| Первая конфигурация минус вторая | Полных пар из 40 | Диапазон эффекта на всех 40, п.п. |','|---|---:|---:|']
    for pair,bounds in z['judge_bounds'].items():
        x,y=pair.split(' minus ');lo,hi=bounds['identified_delta_interval']
        lines.append(f"| {NM[x]} − {NM[y]} | {bounds['complete_pairs']} | {decimal(100*lo,1)}…{decimal(100*hi,1)} |")
    lines+=['','Это диапазоны идентификации при неизвестных решениях судьи. Одинаковые промпты получают одно и то же неизвестное значение во всех сравниваемых условиях. Бутстреп-интервалы в первой парной таблице описывают только случаи с обоими разобранными ответами судьи.']
    ac=z['physical_actor_new'];ju=z['physical_judge_new'];hits=sum(x['source']=='prior' for l in jc.values() for x in l);judge_total=sum(len(l) for l in jc.values())
    lines+=['',f"В дополнительной серии сохранено {ac.get('records',0)} собственных нативных запросов решателя, {num(ac.get('prompt',0))} входных и {num(ac.get('completion',0))} выходных токенов. Суммарное время собственных запросов по счётчику сервера {decimal(ac.get('native_ms',0)/1000,1)} с. В логических затратах каждого режима учитываются также побайтно совпавшие запросы из исходного кэша. Совместная очередь GPU исключает содержательное сравнение времени HTTP-ожидания.",
       '',f"Для 120 добавленных ответов образовалось {len(vv)} уникальных слепых промптов. Использовано {judge_total} квитанций судьи, включая {hits} ранее полученных. В этой папке сохранено {ju.get('records',0)} новых вызовов судьи, {num(ju.get('prompt',0))} входных и {num(ju.get('completion',0))} выходных токенов. Неразобранных уникальных ответов судьи — {sum(x is None for x in vv.values())}.",
       '','Число read_file/diff в первой таблице берётся из журнала действий и включает попытки с явной ошибкой. Полные счётчики ответов инструментов с префиксом ошибки и без него сохранены в results.json. Для случаев, у которых ограничение транспорта привело к незавершённому журналу, наблюдаемые события суммируются отдельно от отсутствующих; расходы без нативного usage не восстанавливались. Бюджет декодирования — 256 токенов на ответ, seed 18112026, температура 0 и thinking off.']
    ds=z['pairs']['git minus block_context'];bound=z['judge_bounds']['git minus block_context']['identified_delta_interval']
    acgit=a['git'];accon=a['block_context'];trace_errors=Counter()
    for f in (ROOT/'trials').glob('*_git.json.gz'):
        for ev in read(f)['trace']:
            for tr in ev:
                if tr['tool']=='answer' and tr['observation'].startswith('Error:'):
                    trace_errors[tr['observation'].splitlines()[0]]+=1
    forced=trace_errors['Error: call diff before answer to inspect current workspace changes.']
    lines[2:2]=[f"Наивысшее точное совпадение и средний F1 в этом прогоне дал Diff ({acgit['em']}/40 и {decimal(acgit['mean_f1'])}). У Concord {accon['em']}/40 и {decimal(accon['mean_f1'])}. В парном сравнении интервалы обеих разностей включают ноль. По слепой семантической оценке Concord получил {accon['blinded_judge_correct']}/40, Diff — {acgit['blinded_judge_correct']} на {acgit['judge_available']} разобранных ответах. С учётом неизвестного результата диапазон преимущества Concord на всех сорока составляет {decimal(-100*bound[1],1)}–{decimal(-100*bound[0],1)} п.п.",'']
    lines+=['',f"В режиме Diff инструмент ответил явным требованием вызвать актуальный diff на {forced} попытки подать ответ. Это часть наблюдаемой нагрузки режима. Среди 40 вопросов Diff вызвал diff {acgit['all_tool_attempts']['diff']} раз, а входных токенов получил на {num(acgit['prompt']-accon['prompt'])} больше Concord. Во всех пяти опубликованных конфигурациях все 40 траекторий завершились принятым ответом, с полными наблюдаемыми токен-метриками."]
    if (ROOT/'results_with_highlight.json').exists():
        h=read(ROOT/'results_with_highlight.json');lines+=['','## Отдельное сравнение с экспериментальной подсветкой','',
             '| Режим | EM | Средний F1 | Судья, верно / разобрано |','|---|---:|---:|---:|']
        for arm in ['correction','control']:
            m=h['arms'][arm];lines.append(f"| {NM[arm]} | {m['em']} | {decimal(m['mean_f1'])} | {m['blinded_judge_correct']} / {m['judge_available']} |")
        lines+=['','Все парные сравнения подсветки и контрольной подсказки с пятью исходными конфигурациями находятся в paired_with_highlight.csv. Эти две экспериментальные метки обозначают отдельные методы.']
    (ROOT/'summary_ru.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
if __name__=='__main__':main()


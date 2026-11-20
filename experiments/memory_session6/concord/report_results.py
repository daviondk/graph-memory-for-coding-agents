"""Render a Russian report from checked scores. No new model calls."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
read=lambda n:json.loads((ROOT/n).read_bytes())
def fmt(n,d=3):
    return f"{n:.{d}f}".replace(".",",")
def interval(x,mult=1,d=3):
    return "["+"; ".join(fmt(mult*z,d) for z in x)+"]"


def render():
    results=read('local_results.json');public=read('published_results.json')
    arms=results['arms'];pairs=results['pairs'];cache=results['cache']
    names={'window':'Concord + свежее окно','baseline':'Исходный Concord','raw':'Исходная история'}
    wb=pairs['window_minus_baseline']
    win,base,raw=(arms[k] for k in ('window','baseline','raw'))
    lines=['# Перечитывание источника после изменения в ConcordBench',
      f"На 40 задачах HotpotQA из ConcordBench-Pioneer квантованный Qwen дал {win['em']} точных ответов при добавлении свежего окна, {base['em']} при исходном Concord и {raw['em']} в режиме сырой истории. Разность окна с исходным Concord {fmt(100*wb['em']['delta'],1)} п.п., 95% парный бутстреп {interval(wb['em']['ci'],100,1)}; точный двусторонний p = {fmt(wb['em']['exact_sign_p'],4)}. Модель получала до трёх актуальных строк в том месте прежнего наблюдения, где Concord обнаружил недействительный фрагмент. Входные данные замерялись для каждого фактического запроса.",
      '## 120 локальных запусков',
      '| Политика | EM из 40 | Средний F1 | Случаи с зарегистрированным вызовом answer | Логических вызовов модели | Учтено токенов вход/выход | Случаи с событиями восстановления |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for k in ['raw','baseline','window']:
        a=arms[k];lines.append(f"| {names[k]} | {a['em']} | {fmt(a['f1'],4)} | {a['submitted_answer']} | {a['requests']} | {a['prompt_observed']} / {a['completion_observed']} | {a['cases_with_race']} |")
    lines+=['## Парные сравнения на одних и тех же задачах',
        '| Разность | Δ EM, п.п. [95% ДИ] | Победы / потери / равенства EM | Δ F1 [95% ДИ] | Одинаковые входы модели на всех шагах |',
        '|---|---:|---:|---:|---:|']
    for key in ['window_minus_baseline','window_minus_raw','baseline_minus_raw']:
        a,b=key.split('_minus_');p=pairs[key];em=p['em'];f=p['f1']
        lines.append(f"| {names[a]} − {names[b]} | {fmt(100*em['delta'],1)} {interval(em['ci'],100,1)} | {em['wins']} / {em['losses']} / {em['ties']} | {fmt(f['delta'],4)} {interval(f['ci'],1,4)} | {p['same_request_sequence_cases']}/40 |")
    # end table: blank-line-separated paragraphs
    lines+=['',f"Различающиеся полные последовательности запросов в основном сравнении получены на {wb['different_request_sequence_cases']} задачах, текст финального ответа различался на {wb['cases_different_answer']}. Добавление окна вызвало {win['extra_reads']} физических перечитываний файлов на {win['cases_refreshed']} задачах. Прочитано {win['extra_bytes']} байт с диска. При промахе кеша реализация читает целый файл, во вход добавляет не более 600 байт отрывка. Сохранённый отрывок мог использоваться повторно. Считая появления заново при каждом логическом запросе, окно присутствовало в {win['model_requests_with_window']} запросах и встретилось в них {win['rendered_window_appearances']} раз.",
       f"Основной контраст по входным токенам в среднем на случай составляет {fmt(wb['prompt']['delta'],1)} {interval(wb['prompt']['ci'],1,1)}, по выходным — {fmt(wb['completion']['delta'],1)} {interval(wb['completion']['ci'],1,1)}. Подробные парные интервалы для действий, событий, запросов, чтений и байтов приведены в local_results.json. Суммы затрат каждой политики считают повторно использованный ответ по числу логических обращений. Дополнительные чтения механизма окна учтены отдельно от вызовов модели и обычного инструмента read_file.",
       f"У {cache['logical_attempts']} логических обращений было {cache['unique_request_keys']} уникальных точных ключей запроса, {cache['physical_successful_receipts']} успешных физических квитанций. Повторения ключей внутри одной траектории — {cache['repeated_in_same_trajectory']}, между режимами одной задачи — {cache['repeated_across_arms_within_case']}, между задачами — {cache['repeated_across_cases']}. На уникальные успешные квитанции пришлись {cache['unique_prompt_observed']} входных и {cache['unique_completion_observed']} выходных токенов. Сумма сообщённого сервером времени обработки входа и генерации — {fmt(cache['unique_model_seconds_observed'],1)} с. Этот счётчик не измеряет длительность развёрнутой политики или сетевые задержки. За пределами указанных финальных траекторий в кеше было {cache['unreferenced_cached_keys']} записей. Отдельно зарегистрировано транспортных отказов по уникальным сохранённым ключам: {cache['transport_failures']}.",
       f"Во всех сравнениях качества знаменатель равен 40. Неизвестных счётчиков действий по порядку raw / Concord / окно: {raw['missing_actions']} / {base['missing_actions']} / {win['missing_actions']}. Логических обращений с отсутствующими данными об использовании токенов: {raw['missing_usage']} / {base['missing_usage']} / {win['missing_usage']}. В парных интервалах затрат учитывались случаи с доступным значением в обеих ветвях. 95%-ные интервалы построены 10 000 повторными выборками задач, общими для ветвей. Дополнительные сравнения описательные.",
       '## Повторная оценка опубликованных ответов',
       '| Авторский актор | Судья авторов, Concord / naive | Точное совпадение, Concord / naive | F1, Concord / naive |',
       '|---|---:|---:|---:|']
    for actor in ['anthropic/claude-sonnet-5','glm-5.2','DeepSeek-V4-Pro']:
        a,b=(public[actor]['arms'][k] for k in ['block_context','naive'])
        lines.append(f"| {actor} | {a['published_judge_correct']} / {b['published_judge_correct']} | {a['em']} / {b['em']} | {fmt(a['f1'],3)} / {fmt(b['f1'],3)} |")
    lines+=['','Проверены 600 опубликованных ответов — три актора, пять политик (включая alert, diff и oracle) и одни 40 вопросов. Каждый EM и F1 пересчитан по тексту, совпадение подтверждено с обеими исходными версиями отчёта. Семантическая оценка GLM-5.2 прочитана из опубликованного решения судьи. Развёрнутый ответ может семантически совпасть с эталоном и получить нулевой EM. Для локальных Qwen-ответов внешнего судьи не запускали. Опубликованные выводы о восстановлении и экономии токенов относятся к другому набору моделей, сравнению с diff и процедуре оценки. [Метод и статья](https://arxiv.org/abs/2610.05281) · [Авторские трассы](https://github.com/FFFFFFFANG1/Concord/tree/4116936349995f0f30597931c0dbbebcbf7e58ac/bench/runs)',
       'Локальный запуск использовал родные инструменты Concord, четыре десятка авторских сценариев, один актор Qwen3.8-27B UD-Q4_K_M, жадное декодирование, контекст 8 192 токена, до 256 выходных токенов за вызов, максимум 30 событий. Промежуточное системное уведомление для шаблона Qwen переводилось в роль user с сохранением текста и позиции (см. revisions/AMENDMENT.md). Окно ориентируется на прежнюю координату источника, поэтому после сдвига строк может показать другое место. Гарантированная частота таких изменений в реальных диалогах неизвестна. Проверка относится к фиксированным задачам и одной реализации чтения. [Протокол](PROTOCOL.md) · [Автономный пересчёт](REPRODUCE.md)']
    out=[]
    for i,line in enumerate(lines):
        if out and line and (line.startswith('#') or out[-1].startswith('#') or (not line.startswith('|') and not out[-1].startswith('|'))) and out[-1]!='':out.append('')
        out.append(line)
    (ROOT/'summary_ru.md').write_text('\n'.join(out)+'\n',encoding='utf8')


if __name__=='__main__':render()

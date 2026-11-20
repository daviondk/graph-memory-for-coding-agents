"""Build the independent second-volume Word report from the locked result files."""
from pathlib import Path
import importlib.util
import json
import os
import sys
from docx.enum.text import WD_ALIGN_PARAGRAPH
import _layout as w

HERE=Path(__file__).resolve().parent
OUT=Path(os.environ.get("MEMORY_NEXT_OUTPUT",str(HERE.parents[1]/"outputs")))
J=lambda n:json.loads((HERE/n).read_text(encoding='utf8'))
ARCHIVE="agent-memory-next-records.zip"
PREVIOUS="agent-memory-benchmark-results.pdf"

def section(path,fn):
    source=HERE/path
    spec=importlib.util.spec_from_file_location(source.parent.name+'_'+source.stem,source)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    getattr(mod,fn)(w)

def write_factor():
    d=J('write_factor/results.json')['cohorts']
    w.page('Запись опыта   /   SWE-ContextBench Lite','Как замена поля правок меняет первую пятёрку',
        'Один и тот же запрос получили шесть вариантов памяти. В каждом индексировались симптом прежней ошибки и заключительная заметка агента. Только третье поле меняло содержание или исключалось.')
    w.p('Для контроля одинакового объёма каждое поле правок передавалось другой истории близкой длины. В библиотеке оставались те же слова, идентификаторы и пути, а также то же число пар «термин — документ». Лексический и гибридный поиск отличались двумя неизменными векторными представлениями. Бюджет выдачи составлял пять прошлых историй на вопрос.')
    names={'lex_absent':'Лексический, поле исключено','lex_shuffle':'Лексический, правки переставлены','lex_real':'Лексический, исходные правки','hyb_absent':'Гибридный, поле исключено','hyb_shuffle':'Гибридный, правки переставлены','hyb_real':'Гибридный, исходные правки'}
    rows=[]
    for key,title in names.items():
        r=d['lite']['methods'][key]
        rows.append([title,f"{r['match1']}/99",f"{r['hit5']}/99",w.dec(r['mrr'],3),w.dec(r['macro_recall5'],3)])
    w.tbl(['Индекс','Верная первая','Есть в пятёрке','MRR','Recall@5¹'],rows,[6.4,3,3,2.3,2.4],True)
    w.p('¹ Hit@5 засчитывает хотя бы одну допустимую связь. Recall@5 усредняет по вопросам долю всех допустимых связей в пятёрке. MRR учитывает обратную позицию первой подходящей истории среди всех 300. Во второй части корпуса связь доступна только для 13 из 258 запросов. У всех шести методов она попала в пятёрку для 12 из этих 13; в подвыборке всего два репозитория.','Caption')
    w.p('В исходном гибридном поиске добавление поля исправило четыре промаха и сохранило предыдущие попадания. По репозиториям 95% интервал разности составил от 0 до +8,33 п. п. При сравнении с переставленными правками исправлены три промаха; интервал от 0 до +5,36 п. п. Для двух основных пар p после поправки Холма равен 0,25. Прежний результат по этому набору уже был известен при постановке опыта.')
    w.p('Во всех четырёх исправленных случаях нужная история и без поля находилась на шестой или седьмой позиции. Две задачи относились к Django, одна к Matplotlib и одна к pytest. Дополнительное поле занимало 197 376 байт текста и 27 933 пары «документ — термин». Восстановлены все прежние первые десятки на 357 запросах, отдельно для лексического и гибридного поиска.')
    w.source('Задачи и траектории из авторской версии SWE-ContextBench','https://github.com/jiayuanz3/SWEContextBench/tree/12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b')

def temporal():
    rows=J('repair/temporal_input/eligibility.json')
    selections={r['id']:r for r in J('repair/temporal_input/selected.json')}
    alt={r['id']:r for r in J('repair/temporal_input/selected_v2.json')}
    w.page('Доступность прошлого опыта   /   Время и происхождение','Что агент мог знать к открытию задачи',
           'Хорошая позиция в библиотеке и доступность информации на момент отладки — два отдельных условия. Прежде чем запускать решателя, для четырёх задач мы проверили даты и номера исходных pull request.')
    labels={'eligible':'Допустим','target_self':'Тот же PR','after_target_issue_open':'Влит позднее'}
    data=[]
    for r in rows:
        x=r['original_frozen_choice'];s=selections[r['id']];a=alt[r['id']]
        idshort=r['repo'].rsplit('/',1)[-1]+' #'+r['id'].rsplit('-',1)[-1]
        data.append([idshort,str(r['target_pr']),str(x['source_pr'])+' · '+labels.get(x['status'],x['status']),str(s['source_pr'] or 'Нет'),str(a['source_pr'] or 'Нет')])
    w.tbl(['Запрос','Целевой PR','Исходный поиск','В опыте¹','Аудит²'],data,[4.2,2.4,5.2,2.6,2.7],True)
    w.p('¹ Для нового запуска из первой десятки гибридного поиска брали наиболее высокую запись из того же репозитория, если её отдельный PR был влит строго до самого раннего открытия связанной целевой задачи. При отсутствии подтверждения источник пропускался. Если доступных записей не оставалось, все режимы получали один и тот же ответ о пустой истории.')
    w.p('² При последующей проверке у источника Requests #2148 совпали номер и репозиторий PR, время открытия с точностью до секунды и полный SHA родительской версии в записи авторов и GitHub. GitHub вернул ошибку 422 при попытке получить старый merge-коммит, поэтому прежняя проверка по родителю его пропустила. При расширенной проверке #2148 допустим для всех трёх запросов Requests. В выполненных эпизодах использованы карточки из столбца «В опыте».')
    w.p('Запросы Requests #3359 и #3481 относятся к одному PR #3574. У них совпадают checkout, эталонная правка и тестовая правка. Они формулируют разные запросы, однако результаты исправления нужно читать и на уровне общего PR. Независимых целевых PR всего три.')
    w.source('Flask #4045, исправление в самой целевой задаче','https://github.com/pallets/flask/pull/4045')
    w.source('Requests #2148, ранее влитый PR, и его временная привязка','https://github.com/psf/requests/pull/2148')
    w.source('Requests #3574, общий PR двух запросов','https://github.com/psf/requests/pull/3574')

def reproduce():
    w.page('Данные и воспроизводимость','Как проверить исследование','В приложенном архиве сохранены протоколы, слепые назначения и прогнозы, индивидуальные решения и оценки. Каждая строка результатов относится к конкретной задаче и варианту памяти.')
    w.tbl(['Каталог','Содержание'],[
        ['write_factor','Шесть полных списков для 357 запросов, происхождение полей, контроль перестановки, проверка 2 142 решений'],
        ['read_policy','Правило чтения и индекс токенов, 99 назначений, полные расходы и парные результаты читателей'],
        ['transfer','Прогнозы по расширенной библиотеке PR, источники дат, срезы покрытия и SHA-256 исходных публичных данных'],
        ['time_read','Допустимые записи для каждого из 99 запросов, все ответы читателя и контроль с поиском только по прошлому'],
        ['abstain','Правила показа или пропуска записи, расходы при равном числе обращений'],
        ['continuation','Передача журнала между двумя отдельными сессиями и её оценка на сохранённых эпизодах'],
        ['map_audit','Опубликованные исходы другого исследования и проверка количественного сопоставления'],
        ['handoff_debt','Назначения и опубликованные исходы для оценки передачи состояния на SWE-bench Verified'],
        ['handoff_policy','Выбор формата передачи с исключением каждого тестируемого проекта из обучения'],
        ['repair','Дайджесты образов, выбор карточки, действия и патчи, официальная оценка, сырые отчёты повторно выполненных команд pytest и замеры модельного сервера']
    ],[4.0,13.1],True)
    w.p('Распакуйте архив и выполните python -B verify.py. Проверка использует сохранённые прогнозы, реальные отчёты оценщика и счётчики локального сервера. В README_RU.md указаны зависимости для воспроизведения. Сравнение дальнейших направлений и условия проверки кандидата в статью изложены в NEXT_STUDY_RU.md. Манифест сверяет содержимое всех файлов архива.')
    native=J('repair/runtime/reconciled.json')
    w.p(f"Локальный сервер зарегистрировал {native['native_calls']} новых вызовов Qwen, {w.n(native['prompt_tokens'])} входных токенов и {w.n(native['completion_tokens'])} токенов ответа. Из них 288 вызовов относятся к ремонту, 64 к продолжению, 113 к чтению допустимой истории и 40 к записи исходов pytest. Переоценка внешних архивов и реконструкция старых решений в эти расходы не входят.")
    w.source('Архив прогнозов, вызовов, патчей и оценок этого тома',ARCHIVE)
    w.source('Предыдущий экспериментальный отчёт, 35 страниц сравнений',PREVIOUS)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    w.doc.core_properties.title='Как кодовому агенту сохранять, читать и передавать опыт'
    w.p('ЭКСПЕРИМЕНТАЛЬНЫЙ ОТЧЁТ     /     НОЯБРЬ 2026','Section line')
    w.p('Как кодовому агенту сохранять, читать и передавать опыт','Title')
    w.p('Поиск по прошлым правкам, доступность памяти к началу задачи и передача незавершённой работы следующей сессии.','Lead')
    section('front.py','cover')
    write_factor()
    section('permutation_section.py','add_permutations')
    section('read_policy/report_section.py','add_policy')
    section('transfer/report_section.py','add_transfer')
    section('time_read/report_section.py','add_time_read')
    section('abstain/report_section.py','add_abstain')
    temporal()
    section('repair/report_section.py','add_repair')
    section('repair/pipe_check/report_section.py','add_pipe')
    section('continuation/report_section.py','add_continuation')
    section('handoff_policy/report_section.py','add_handoff_policy')
    section('map_audit/report_section.py','add_map')
    section('front.py','interpret')
    reproduce()
    z=OUT/ARCHIVE
    if not z.exists():raise FileNotFoundError(z)
    part=w.Part(w.PackURI('/word/embeddings/research-records.zip'),'application/zip',z.read_bytes(),w.doc.part.package)
    w.doc.part.relate_to(part,'http://schemas.openxmlformats.org/officeDocument/2006/relationships/package')
    temp=OUT/'agent-memory-next-results.partial.docx'
    w.doc.save(temp)
    temp.replace(OUT/'agent-memory-next-results.docx')

if __name__=='__main__':main()


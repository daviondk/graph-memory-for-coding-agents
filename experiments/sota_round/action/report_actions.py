"""Generate a Russian-language result page from the complete, checked cell ledger."""
import argparse
import csv
import json
from pathlib import Path


def pct(x):
    return f"{100*x:.1f}".replace(".",",")


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("study",type=Path)
    cli.add_argument("--plain",action="store_true")
    args=cli.parse_args()
    data=json.loads((args.study/"action_results.json").read_text("utf-8"))
    arms=data["arms"]
    labels={"receipt":"Карточка из завершения сессии","raw":"Лучшие фрагменты BM25","empty":"Без памяти"}
    title="Повтор с ответом в виде Python" if args.plain else "Основной опыт с ответом в виде JSON"
    out=[f"# {title}","",
          "Каждая из 34 задач решалась во всех трёх условиях одним локальным Qwen3-8B с жадным декодированием. Вход содержал запрос и исходные файлы. В условиях с памятью использовались одни и те же две сессии и общий предел в 300 слов. Модель генерировала программу, изменяющую рабочую копию. Успех определял исходный исполняемый проверяющий модуль авторов задачи.","",
          "| Условие | Успехи / 34 | Исполнилось без ошибки | Дословный заполнитель | Среднее число слов памяти | Медиана входных токенов |",
          "|---|---:|---:|---:|---:|---:|"]
    for name in ("receipt","raw","empty"):
        row=arms[name]
        out.append(f"| {labels[name]} | {row['successes']}/34 | {row['builder_counts'].get('ok',0)}/34 | {row['echoed_placeholder']} | {row['memory_words']['mean']:.1f} | {row['input_tokens']['median']:g} |")
    c=data["prompt_cost"]
    fetched=data["strata"].get("all_precursors_fetched_True",{}).get("n",0)
    out+=["",f"На все 34 запроса карточки потребовали {c['receipt_tokens']} входных токенов, исходные фрагменты — {c['raw_tokens']}. Разница — {c['fewer_tokens']} токенов ({pct(c['relative_to_full_raw'])}% от полного входа с фрагментами, {pct(c['relative_to_raw_increment'])}% от добавки сверх условия без памяти). Для обеих форм памяти найденная пара сессий включала весь предусмотренный авторами набор предшествующих сессий в {fetched} из 34 задач."]
    out+=["","## Парные исходы","",
          "| Сравнение | Выигрыши | Потери | Одинаковый исход | Разница, п. п. | Точный двусторонний p |",
          "|---|---:|---:|---:|---:|---:|"]
    for cmp,lbl in [("receipt_minus_raw","Карточка против фрагментов"),("receipt_minus_empty","Карточка против отсутствия памяти"),
                    ("raw_minus_empty","Фрагменты против отсутствия памяти")]:
        x=data["paired"][cmp]
        out.append(f"| {lbl} | {x['wins']} | {x['losses']} | {x['ties']} | {pct(x['delta'])} | {x['exact_two_sided_mcnemar']:.4g} |")
    x=data["paired"]["receipt_minus_raw"]
    sensitivity=data["sensitivity_without_bool"]
    examples=[]
    if x["fixed"]:
        examples.append("Рабочее решение с карточкой при неудаче исходных фрагментов получено для "+", ".join(x["fixed"])+".")
    if x["harmed"]:
        examples.append("Рабочее решение с фрагментами при неудаче карточки получено для "+", ".join(x["harmed"])+".")
    examples.append(f"При исключении ts-bool-env размер выборки уменьшился до {sensitivity['n']}. Число выигрышей карточки относительно фрагментов составило {sensitivity['wins']}, число потерь — {sensitivity['losses']}, точный p = {sensitivity['exact_two_sided_mcnemar']:.4g}.")
    out+=[""," ".join(examples),"",
          "## Качество измерения","",
          "Перед оцениванием прошли все 34 эталонных решения с решающим фактом. Ожидаемо провалились все 34 наивных решения и все 34 неизменённых дерева. Проверка изоляции подтвердила, что программе выдаются только рабочее дерево, её исходник и системная среда Linux, а наружу нет сетевого маршрута.","",
          f"Количество срабатываний лимита в 1 280 токенов по условиям «карточка / фрагменты / без памяти» — {arms['receipt']['at_output_limit']} / {arms['raw']['at_output_limit']} / {arms['empty']['at_output_limit']}. Ошибок инфраструктуры проверяющего модуля — {sum(a['infrastructure'] for a in arms.values())}. В знаменателе сохранены все 102 назначения, включая неисполняемый ответ. Для программы, завершившейся с ошибкой, проверялось фактически оставленное дерево файлов.","",
          "Один детерминированный прогон покрывает 34 авторские задачи и один способ обращения к модели. Реальные задержки генерации получены для пакетов из шести контекстов. Влияние вида памяти на общую задержку из этих пакетов выделить нельзя. Результаты не переносились на официальный рейтинг продуктов или другие модели."]
    if args.plain:
        out+=["","Вариант с Python был зафиксирован после обнаружения, что в первой серии некоторые ответы дословно копировали пример значения JSON. Все 102 назначения повторены с одинаковыми задачами, моделью и расположением в пакете. Причинная интерпретация межсерийной разницы охватывает изменение текста инструкции вместе с формой вывода."]
    else:
        n=sum(a["echoed_placeholder"] for a in arms.values())
        out+=["",f"В {n}/102 ответах модель вернула буквальный текст «complete Python 3 source» вместо исполнимого кода. Это ограничивает возможность оценить полезность памяти в данной серии. JSON с таким значением корректен синтаксически, однако соответствующее рабочее дерево не выполняет задачу."]
    if x["fixed"] or x["harmed"]:
        with (args.study/"action_per_cell.csv").open(encoding="utf-8",newline="") as f:
            cells={(r["task"],r["arm"]):r for r in csv.DictReader(f)}
        out+=["","## Расхождения между двумя представлениями памяти","",
              "Приведены все задачи, где критерий функциональной корректности дал разный исход у карточки и исходных фрагментов. Сообщения проверяющего модуля сохранены на английском языке.","",
              "| Задача | Карточка | Фрагменты |","|---|---|---|"]
        for task in sorted(x["fixed"]+x["harmed"]):
            def display(arm):
                rec=cells[task,arm]
                s=" ".join(rec["verdict"].split()).replace("|","\\|")
                return ("✓ " if rec["ok"]=="True" else "✗ ")+(s[:177]+"…" if len(s)>180 else s)
            out.append(f"| {task} | {display('receipt')} | {display('raw')} |")
    (args.study/"action_report_ru.md").write_text("\n".join(out)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()

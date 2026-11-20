"""Russian results page for the paired continuation study."""
import csv
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent

def add_continuation(w):
    s=json.loads((ROOT/"results.json").read_text(encoding="utf-8"))
    with (ROOT/"per_run.csv").open(encoding="utf-8",newline="") as f:
        rows=list(csv.DictReader(f))
    a=s["arms"]["manifest"]; b=s["arms"]["last_two"]
    w.page("Передача незавершённой работы", "Какие действия сообщать следующему агенту",
           f'После передачи журнала официальный оценщик засчитал {a["solved"]} из 4 исправлений. При передаче последних двух действий засчитано {b["solved"]} из 4.')
    w.p("Взяли четыре заранее выбранные задачи Flask и Requests после ветви brief. Каждую передали в две чистые сессии Qwen3.8-27B Q4_K_M с одинаковым образом, патчем, issue, исходной карточкой памяти и двумя последними действиями. Дополнительный блок в одном условии перечислял явные обращения к файлам, тестовые команды, ошибки, изменённые пути и повторы команд. Все предшественники исчерпали 24 вызова, четыре исходных патча пусты. Проверяется передача сделанных наблюдений при чистом дереве. У преемника ещё восемь вызовов, порядок задан хешем, seed одинаков в паре.")
    def yn(v):return "да" if v else "нет"
    vals=[]
    for pair in s["pairs"]:
        iid=pair["target"]
        rr={r["arm"]:r for r in rows if r["id"]==iid}
        vals.append((iid.split("__")[-1],yn(pair["baseline_solved"]),yn(pair["last_two_solved"]),yn(pair["manifest_solved"]),
                     rr["last_two"]["previous_command_repeats"]+" / "+rr["manifest"]["previous_command_repeats"]))
    w.tbl(["Задача","Решена до передачи","Два действия","С журналом","Повторы команд, два / журнал"],
          vals,[3.2,3.1,3.0,3.0,4.8],True)
    w.p(f'В парном сравнении у журнала выигрышей {s["wins"]}, проигрышей {s["losses"]}, ничьих {s["ties"]}. Изменение доли исправлений {s["difference_pp"]:+.0f} п.п. Точный двусторонний p = {s["p_exact_descriptive"]:.3f}. Все восемь итоговых патчей пусты. Официальный оценщик вернул No patch до исполнения F2P/P2P. Каждая строка — одна постановка задачи. Две постановки Requests ссылаются на общий целевой PR.')
    w.tbl(["Ресурсы и действия, сумма","Последние два действия","Сводка действий"],
          [(name,b[k],a[k]) for name,k in [("Вызовы модели","calls"),("Входные токены","input_tokens"),
               ("Выходные токены","output_tokens"),("Команды оболочки","shell_commands"),
               ("Повторы старых тестовых команд","previous_test_repeats"),("Изменён исходный патч, задач","final_changed_vs_initial")]],
          [7.4,4.9,4.8],True)
    w.p("Повтор определяется точным совпадением команды после нормализации пробелов. Журнал сообщает статус внешней оболочки. В 7 из 12 явных старых тестовых команд оболочка вернула 0 при маркере неудачи в выводе, 6 таких команд попали в журнал. Хеш восстановленного патча одинаков у обеих ветвей. Временные файлы и процессы в передачу не входят. Один seed и два репозитория ограничивают обобщение.","Caption")
    import importlib.util
    spec=importlib.util.spec_from_file_location("handoff_debt_report",ROOT.parent/"handoff_debt"/"report_section.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.add_handoff_debt(w)


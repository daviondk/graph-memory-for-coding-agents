"""Two independent pages: fixed pre-task memory and one-call interventions inside the agent."""
import json
from pathlib import Path

DATA=Path(__file__).resolve().parents[1]/"vibe"
PAPER="https://arxiv.org/abs/2609.23570"
CHECKER="https://github.com/AlibabaResearch/DAMO-ConvAI/blob/7152cf96809b45343ccc1caf7115a7d3fa43f956/VibeMemBench/scripts/vendor/eval.py"
AGENT="https://github.com/SWE-agent/mini-swe-agent/tree/bc85a45654e6348dcc6e4c5a40ad146ed0bb144d"
MODEL="https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/tree/4af51b3542f775b0a8e4b310bfb3f17e01c306c9"
LABEL={"base":"Без памяти","distractor":"Плацебо","raw_bm25":"BM25, сырая запись","action_receipt":"Действия и проверки","prior_files":"Файлы прошлых правок","path_trigger":"При совпадении пути","fixed_third":"После 3-го результата"}

def number(v):
    return f"{int(v):,}".replace(","," ")

def load(folder,file):
    return json.loads((DATA/folder/file).read_text(encoding="utf8"))

def compact(v):
    return "/".join(str(int(x)) for x in v)

def add_strong(w):
    strong=load("qwen38_27b","results.json")["by_method"]
    planned=load("","prospective_27b.json")
    ids=[t["instance_id"] for t in planned["targets"]]
    w.page("VibeMemBench  /  Решение задач","Что изменилось с агентом Qwen3.8-27B",
        "В двух заранее выбранных репозиториях проведено 20 запусков. Каждый из пяти вариантов подсказки получил по две попытки на каждой задаче.")
    w.p("Агент mini-SWE-agent работал в исходных образах с закреплённой версией кода. На попытку выделили 30 обращений к модели, каждое до 1 024 новых токенов. Модель Qwen3.8-27B в квантовании UD-Q4_K_M использовала контекст 49 152 токена и температуру 0,5. Начальные случайные числа совпадали между условиями внутри задачи и повтора.")
    table=[]
    for arm in planned["methods"]:
        a=strong[arm];t=a["totals"]
        table.append([LABEL[arm],compact(a["per_target"][ids[0]]),compact(a["per_target"][ids[1]]),str(a["resolved"])+"/4",str(a["nonempty_patches"]),number(t["output_tokens"])])
    w.tbl(["Материал для агента","brutils¹","schema¹","Решено","Патчи","Токены²"],table,small=True)
    w.p("¹ Две цифры соответствуют seed 0 и seed 1. Единица означает, что официальный оценщик принял решение. Столбец brutils обозначает brutils-python, schema — dataclasses-jsonschema. ² Сумма выходных токенов за четыре запуска условия.")
    score=strong["prior_files"]["resolved"];raw=strong["raw_bm25"]["resolved"];plain=strong["base"]["resolved"];receipt=strong["action_receipt"]["resolved"]
    w.p(f"Запись файлов прошлых правок дала {score} из 4 успешных попыток, поиск BM25 — {raw}, краткая история действий — {receipt}, отсутствие памяти — {plain}. Успех требует прохождения всех тестов FAIL_TO_PASS и PASS_TO_PASS. Положительный и отрицательный контроли первоначально проверили чувствительность оценщика на обеих задачах.")
    w.p("Независимых задач две. Различия между повторными запусками относятся к выбранным репозиториям, конкретным карточкам и модели. При сравнении с пилотом 8B одновременно изменились модель, квантование и бюджет действий.")
    w.source("Открытый оценщик исправлений VibeMemBench",CHECKER)
    w.p("После девяти завершённых эпизодов Windows перезапустилась с кодом 0x133. У прерванной попытки сохранились 22 ответа, 217 256 входных и 2 692 выходных токена. Это отдельный расход. Попытка заново началась с того же seed. При восстановлении отключили серверный кэш предыдущих запросов в оперативной памяти. Модель, контекст и параметры генерации сохранили.","Caption")
    w.source("Зафиксированная версия весов Qwen3.8-27B",MODEL)
    add_in_loop(w,strong)

def add_in_loop(w,strong):
    info=load("in_loop","delivery.json")
    cfg=load("in_loop","protocol.json")
    ids=[t["instance_id"] for t in cfg["targets"]]
    rows=info["rows"]
    w.page("VibeMemBench  /  Память внутри решения","Одно чтение памяти между ходами агента",
        "На тех же двух задачах выполнено восемь новых запусков. В каждом агент мог увидеть одну и ту же историческую запись максимум на одно обращение к модели.")
    w.p("В первом условии подсказка появлялась после выполненного чтения или поиска, когда в команде либо её ответе находился полный путь из прежней правки. Во втором условии запись появлялась после третьего результата инструмента независимо от текста. При отсутствии подходящего события агент продолжал работу без подсказки.")
    table=[]
    for arm in cfg["methods"]:
        a=[r for r in rows if r["method"]==arm]
        table.append([LABEL[arm],compact([r["resolved"] for r in a if r["target"]==ids[0]]),compact([r["resolved"] for r in a if r["target"]==ids[1]]),
            str(sum(r["exposed"] for r in a))+"/4",str(sum(r["extra_prompt_tokens"] for r in a)),str(sum(r["resolved"] for r in a))+"/4"])
    w.tbl(["Момент выдачи","brutils¹","schema¹","Выдач","Δ токенов²","Решено"],table,small=True)
    w.p("¹ Показаны оценки для seed 0 и seed 1 в том же порядке, что на предыдущей странице. ² Сколько токенов суммарно добавила подсказка к реальному входу модели непосредственно при выдаче.")
    detail=[]
    for arm in cfg["methods"]:
        a=[r for r in rows if r["method"]==arm]
        pos=[str(r["tool_result_index"]) if r["exposed"] else "—" for r in a]
        detail.append(LABEL[arm].lower()+" — "+", ".join(pos))
    w.p("Номера результатов инструмента, после которых агент увидел карточку, перечислены по репозиторию и повтору. "+". ".join(detail)+".")
    w.p("Прокси добавлял запись в копию истории на входе модели. На следующих вызовах надстройка исчезала. Собственные действия агента, ответы инструментов и изменения в рабочем дереве сохранялись. Проверены связанные идентификаторы инструментов, хеши пересланных историй и учёт токенов.")
    w.p(f"Вторичные условия с исходной страницы дали {strong['base']['resolved']}/4 без памяти и {strong['prior_files']['resolved']}/4 при постоянной той же записи. Две логики выдачи меняют одновременно момент и вероятность показа. Эти свойства по отдельности здесь не оценены.")
    w.source("Агент и протокол событий инструментов",AGENT)
    w.p("У двух из четырёх пар момент выдачи совпал. В одной из них результат исправления разошёлся. Первое чтение каталога включало разные временные метки контейнера. При фиксированном seed тексты наблюдений могут различаться до первой подсказки.","Caption")
    w.source("Постановка VibeMemBench и единица измерения",PAPER)

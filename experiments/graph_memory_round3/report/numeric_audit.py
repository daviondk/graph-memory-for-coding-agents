"""Recalculate selected headline cells and compare with Russian manuscript text."""
import hashlib
import json
from pathlib import Path

here = Path(__file__).resolve().parent
base = here.parent
sources = {}
checks = []


def read(path):
    data = (base / (path + ".json")).read_bytes()
    sources[path] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def val(x):
    return str(x).replace(".", ",")


def percent(x, digits=2):
    return f"{x * 100:.{digits}f}".replace(".", ",") + "%"


def cell(page, label, values):
    path = here / "pages" / (page + ".md")
    rows = [s.strip("|").split("|") for s in path.read_text("utf8").splitlines() if s.startswith("|")]
    actual = next(row for row in rows if row[0].strip() == label)[1:]
    norm = lambda a: "".join(a.split()).replace("*", "").replace("−","-")
    for out, ref in zip(actual,values):
        assert norm(out) == norm(val(ref)), (page, label, out, ref)
        checks.append([page, label, out.strip()])
    assert len(actual) >= len(values)


def expect(page, values):
    body = (here / "pages" / (page + ".md")).read_text("utf8").replace(" ", "")
    for x in values:
        expected = val(x).replace(" ", "")
        assert expected in body, (page, x)
        checks.append([page, "running text", expected])


a = read("writer/results")["arms"]
b = read("writer/optimal_results")["arms"]
for k, label in [('lru','По давности обращения'),('point','По ценности отдельных страниц'),('global','Целые группы, общая ширина'),('typed','Целые группы, условная ширина'),('placebo','Переставленные характеристики')]:
    cell("02", label, [a[f"{k}@{n}"]["hits"] for n in (4096,12288)] + [b[f"{k}@{n}"]["whole"] for n in (4096,12288)])
expect("03", [b[f"{k}@4096"]["whole"] for k in ("chain_exact","additive_exact")])
wr=read("writer/chain_results")["arms"]
expect("03", [wr[f"{w}/typed/{n}"]["whole"] for w in ("typed","point") for n in (4096,12288)])
ser = read("serialized_writer/results")
for k,label in [('point','Обычная оценка отдельных страниц'),('typed','Сохранение связанных групп')]:
    cell("06", label, [ser['arms'][f"{k}@{n}"]["hits"] for n in (4096,12288)])
curves = read("serialized_writer/curve_results")
assert all(curves["curves"][f"{k}@24576"]["hits"] == curves['gold_in_unbounded_memory'] for k in ("typed","point","lru"))
expect("06", [curves['gold_in_unbounded_memory']])
d = read("demand/results")
cell("06b","Brier для вида действия",[f"{d['brier'][k]:.3f}" for k in ("fixed","adaptive")])
cell("06b","Доля доступных строк при просмотре",[percent(d['groups']['view']['scores'][k]['frac'],1) for k in ("fixed","adaptive")])
cell("06b","Полностью доступны, из 652 правок",[d['groups']['edit']['scores'][k]['whole'] for k in ("fixed","adaptive")])
cell("06b","Средняя смешанная полезность",[percent(d['groups']['all']['scores'][k]['utility'],1) for k in ("fixed","adaptive")])
ctx = read("context/results")["budget"]
ctx_b = read("context/replication/results")["budget"]
for k,label in [('recent','По давности'),('r2f','Прежние страницы R2-F'),('fixed','Фиксированное окно'),('flat','Гибкие окна, общая ширина'),('typed','Гибкие окна, условная ширина')]:
    cell("04",label,[arm[n]["arms"][k]["hits"] for arm in (ctx,ctx_b) for n in ("256","512")])
exp=[read("context/"+directory+"expansion_results")['budget']['512']['arms'] for directory in ('','replication/')]
fmt=[read("context/"+directory+"serializer_results")['results'] for directory in ('','replication/')]
cell("05","Исходный выбор R2-F",[m['r2f']['hits'] for m in exp])
cell("05","Слияние одинаковых адресов и расширение",[m['iso_balanced']['hits'] for m in exp])
for k,label in [('shared','Тот же тест при записи пути один раз на файл'),('body','Формат только с текстом без адреса')]:
    cell("05",label,[f"{m[k]['arms']['typed']['hits']} против {m[k]['arms']['r2f']['hits']}" for m in fmt])
repo=read("repo/results")["all"]["metrics"]
for k,label in [('owner','Владелец объявления'),('transition','Контекст предыдущего обращения')]:
    cell("07",label,[repo[k]['hits'][0],f"{repo[k]['mrr']:.3f}"])
rept=read("repo/transfer_results")["all"]["metrics"]
expect("07",[rept[k]['hits'][0] for k in ("transition","owner","gate","mix")])
bud=read("repo/token_results")
expect("07",[bud[q]['hits'][k] for q in ("original_512","transfer_512") for k in ("transition","owner")])
ext=read("repo/external_results")
for k,label in [('sem_bm','BM25 на общей выборке'),('transition3','Граф прошлых использований'),('reported_semlith','Semlith, результаты авторов')]:
    cell("07b",label,[sum(row[k][j] for row in ext.values()) for j in (0,1)])
ret=read("qa/retrieval_results")['results']
for k,label in [('bm25','BM25'),('dense','Плотный MiniLM'),('flat','Обучаемый плоский контроль'),('attribution','Только привязка местоимений'),('graph','Привязка и направление ответа'),('placebo','Перестановка назначений')]:
    m=ret['turn']['metrics'][k]
    cell("09",label,[percent(m['all@5']),percent(m['any@5']),f"{m['mrr@10']:.3f}",percent(ret['session']['metrics'][k]['all@5'])])
conv=read("qa/conversational_results")
for k,label in [('dialog','Прямое диалоговое'),('implicit','Неявное'),('counterfactual','С ложным утверждением'),('composed','Составное')]:
    m=conv[k]
    cell('10',label,[m['n'],percent(m['means']['flat']['all@5']),percent(m['means']['graph']['all@5'])])
off=read("qa/official_conv_results")['results']
for k,label in [('flat','Плоский контроль R3'),('graph','Граф авторства R3')]:
    cell('10b',label,[percent(off[k]['by_style'][field]['macro_recall']) for field in ("dialog","implicit","counterfactual","composed")])
trans=read("qa/transfer_results")["means"]
matched=read("qa/matched_reader_results")["means"]
for m,label in [(trans['flat'],'Исходный текст, плоский поиск'),(trans['graph'],'Исходный текст, графовый поиск'),(trans['owner'],'Только имена, графовый поиск'),(trans['date'],'Только даты, графовый поиск'),(trans['joint'],'Имена и дата, графовый поиск'),(trans['wrong_date'],'Имена и неверная дата, графовый поиск'),(matched['flat_joint'],'Имена и дата, плоский поиск')]:
    cell('11',label,[f"{m['f1']*100:.2f}",f"{m['em']*100:.2f}",f"{m['tokens']:.1f}"])
online=read("class_memory/online_results")["scores"]
for field,label in [('pass_all','Прошли все тесты класса, из 14'),('method','Прошли профильные тесты метода, из 54'),('integration','Прошёл интеграционный набор, из 14'),('tests','Отдельные проверки, из 293'),('prompt','Входные токены, логическая сумма'),('completion','Выходные токены, логическая сумма')]:
    cell('08b',label,[online[k][field] for k in ('graph','bm25_line','full')])
real=read("real_swe/results")['arms']
for k,label in [('lru','Вытеснение по давности'),('point','Оценка отдельных страниц'),('typed','Полезность целых групп')]:
    cell("06c",label,[real[k]['hits'],percent(real[k]['fraction']),real[k]['start']])
geometry=read("geometry_results")["SWE-bench Verified A"]
for geo in ("one_page","multiple_pages"):
    row=geometry[geo]
    expect("06c",[row['n']]+[s['full'] for s in row['arms'].values()])
if (base/"class_memory/results.json").is_file() and (here/"pages/08.md").is_file():
    classical=read("class_memory/results")["main"]["scores"]
    names={"none":"Пустая память","bm25_method":"BM25 по методам","bm25_line":"BM25 по строкам","graph":"Граф полей и зависимостей","placebo":"Переставленные веса","full":"Доступный текст до 800 токенов"}
    for k,label in names.items():
        cell("08",label,[classical[k][n] for n in ("pass_all","passed","memory_tokens")])
follow=read("real_swe_followup/results")['arms']
for k,label in [('lru','Вытеснение по давности'),('point','Оценка отдельных страниц'),('typed','Замороженный граф'),('mixed','Выбор по размеру наблюдения')]:
    cell("06d",label,[follow[k]['hits'],percent(follow[k]['fraction']),follow[k]['start']])
out = dict(checked_values=len(checks), source_sha256=sources, checks=checks)
(here / "final/numeric_audit.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf8")
print("matched",len(checks),"headline values from",len(sources),"source files")

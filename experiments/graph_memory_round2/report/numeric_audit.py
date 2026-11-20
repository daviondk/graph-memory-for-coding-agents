"""Validate the published tables through physical DOCX cells and frozen experiment outcomes."""
from pathlib import Path
from docx import Document
import json
import re

here=Path(__file__).resolve().parent
root=here.parent
doc=Document(here/"final/graph-memory-research-round2.docx")
def get(rel):
    return json.loads((root/rel).read_text(encoding="utf-8"))
tables={}
for t in doc.tables:
    rows = [[c.text.strip() for c in r.cells] for r in t.rows]
    tables[rows[0][0]]=rows
def numbers(key):
    return [[int(re.search(r"\d+",s.replace("\xa0","").replace(" ","")).group()) for s in row[1:]] for row in tables[key][1:]]
def counts(key):
    return [s[0] for s in numbers(key)]
cases={}
def chk(k,actual,expected):
    assert actual==expected, (k,actual,expected)
    cases[k]={"actual":actual,"expected":expected}
a=get("localization/grounding/results.json")
chk("A2",numbers("Как обучали правило"),[[a[s]["totals"][m]["any"]["hit"] for m in ["native","flat","graph"]] for s in ["loc_loro","river_loro","river_time","river_zero"]])
b=get("multihop/results.json")["test"]["totals"]
chk("B",counts("Правило"),[b[s]["hits"] for s in ["flat","graph","origin","shuffle","beam"]])
bt=get("multihop/typed_results.json")
chk("B3",counts("Содержимое памяти и чтение"),[bt["hits"][s] for s in ["graph","roles","roles_whole","whole_edge","whole_shift","beam"]])
c=get("attempt_memory/results.json")
cn=numbers("Селектор программы")
chk("C",cn[:4]+cn[-1:],[[c[s]["all"]["solved"][m] for s in ["fresh","old"]] for m in ["single","first_public","short","value","pool_oracle"]])
d=get("failure_policy/score.json")["results"]
ds=get("failure_policy/sensitivity.json")["all_results"]
chk("D",numbers("Формат или правило"),[[d[s]["solved"],ds[s]["strict_k"]] for s in ["NONE","HISTORY","REFLECT","SIGNAL","BOTH","constant_cv","ridge","graph","placebo"]])
e=get("edit_memory/results.json")["cases"]["sums"]
chk("E",numbers("Политика чтения"),[e[s] for s in ["recent","base","flat","address","full","placebo"]])
f=get("span_memory/results.json")["hits"]
chk("F",counts("Политика выдачи до трёх страниц"),[f[s] for s in ["pointwise","recent","global","history","typed","placebo"]])
budget=get("span_memory/budget_results.json")["budget"]
chk("F-token",numbers("Правило при равном бюджете"),[[budget[b]["hits"][s] for b in ["256","512"]] for s in ["recent","pointwise","global","history","typed","placebo"]]+[[budget[b]["upper_bound"] for b in ["256","512"]]])
w=get("span_memory/window_results.json")
alltext=" ".join(p.text for p in doc.paragraphs).replace("\xa0"," ")
assert f'дали {w["baselines"]["point_center"]["hits"]} и {w["baselines"]["point_forward"]["hits"]}, условная длина — {w["typed"]}' in alltext
assert f'дало {w["baselines"]["recent_center"]["hits"]} и {w["baselines"]["recent_forward"]["hits"]} попаданий' in alltext
ac=get("span_memory/audit_independent.json")["posthoc_first_accepted_sensitivity"]
assert str(ac["all_eligible"]) in alltext.replace(" ", "") and f'покрывает {ac["hits"]["typed"]} правки целиком, общая модель длины — {ac["hits"]["global"]}' in alltext
(here/"final/numeric_audit.json").write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding="utf-8")
print("Validated report cell content:", ", ".join(cases))

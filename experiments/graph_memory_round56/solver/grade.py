"""Execute each distinct generated implementation, tracking exact case denominators."""
import itertools
import re
import statistics
import textwrap
from collections import Counter
from study import *
from isolation import execute

def parse_answer(text,name):
    chunks=re.findall(r"```(?:python)?\s*\n(.*?)```",text,flags=re.S|re.I)
    source=textwrap.dedent(chunks[0] if chunks else text).strip()
    try:tree=ast.parse(source)
    except (SyntaxError,ValueError):return "", "parse_error"
    if len(tree.body)!=1 or not isinstance(tree.body[0],ast.FunctionDef) or tree.body[0].name!=name:return "","wrong_function"
    node=tree.body[0]
    forbidden=set("open eval exec compile __import__ input breakpoint os sys pathlib subprocess socket requests ctypes importlib pickle builtins globals locals vars __dict__ __class__ __globals__ __subclasses__ __builtins__".split())
    allowed=set("collections calendar datetime decimal enum fractions functools heapq itertools math operator re statistics string typing unicodedata bisect copy".split())
    for x in ast.walk(node):
        if isinstance(x,(ast.Global,ast.Nonlocal)) and isinstance(x,ast.Global):return "","unsafe_global"
        if isinstance(x,ast.Name) and x.id in forbidden:return "","unsafe_name"
        if isinstance(x,ast.Attribute) and x.attr in forbidden:return "","unsafe_attr"
        if isinstance(x,(ast.Import,ast.ImportFrom)):
            roots=[n.name.split(".")[0] for n in x.names] if isinstance(x,ast.Import) else [(x.module or "").split(".")[0]]
            if any(root not in allowed for root in roots):return "","unsupported_import"
    return ast.unparse(node),"ok"

def signflip(group_sums):
    obs=abs(sum(group_sums))
    return statistics.fmean(abs(sum(a*b for a,b in zip(group_sums,signs)))>=obs-1e-12
                            for signs in itertools.product((-1,1),repeat=len(group_sums)))

def aggregate(records,assign):
    out={}
    for arm in ARMS:
        vals=[r[arm] for r in records.values()]
        out[arm]=dict(pass1=sum(x["ok"] for x in vals),n=len(vals),passed_examples=sum(x["good"] for x in vals),examples=sum(x["total"] for x in vals),
                      macro_example_fraction=statistics.fmean(x["good"]/x["total"] for x in vals),
                      status=dict(Counter(x["status"] for x in vals)))
    contrasts={}
    for other in ARMS[1:]:
        delta={q:int(r["file8"]["ok"])-int(r[other]["ok"]) for q,r in records.items()}
        byg=[sum(v for q,v in delta.items() if q.startswith(repo+"|")) for repo in SPECS]
        contrasts[other]=dict(wins=sum(v==1 for v in delta.values()),losses=sum(v==-1 for v in delta.values()),
                 ties=sum(v==0 for v in delta.values()),delta_pp=100*sum(delta.values())/len(delta),
                 signflip_repo_p=signflip(byg),by_repo=byg,
                 different_prompts=sum(assign[q]["file8"]["hash"]!=assign[q][other]["hash"] for q in delta))
    return out,contrasts
def main():
    seal=read("answer-seal.json")
    assert digest((HERE/"answers.json.gz").read_bytes())==seal["answers"] and digest((HERE/"input-seal.json").read_bytes())==seal["input"]
    a=read("answers.json.gz");c=read("assignments.json.gz");sel=read("selections.json.gz");cal=read("calibration.json.gz")
    jobs={};marks={}
    for q,refs in c.items():
        t=sel[q]["task"]
        for arm,info in refs.items():
            h=info["hash"];i=q+"|"+h
            if i in marks:continue
            fun,status=parse_answer(a[h]["text"],t["name"]);marks[i]=status
            if fun:
                jobs[i]=dict(id=i,repo=t["repo"],path=t["path"],name=t["name"],kind="model",answer=fun)
    measured=execute(list(jobs.values()))
    records={}
    for q,refs in c.items():
        total=cal[q+"|reference"]["run"];rec={}
        for arm,info in refs.items():
            k=q+"|"+info["hash"];meas=measured.get(k,{})
            if meas.get("run")==total:good=total-meas["failed"]
            else:good=0
            rec[arm]=dict(ok=good==total,good=good,total=total,
                          status=("pass" if good==total else "failed_examples") if meas.get("run")==total
                          else marks[k] if k not in measured else "isolated_runtime_failure",h=info["hash"])
        records[q]=rec
    write("execution.json.gz",dict(measured=measured,parse_status=marks))
    write("records.json.gz",records)
    totals,pairs=aggregate(records,c)
    result=dict(n=len(records),summaries=totals,file8_vs=pairs,
                by_project={repo:aggregate({q:r for q,r in records.items() if q.startswith(repo+"|")},c)[0]
                            for repo in SPECS})
    write("results.json",result)
    print("tested",len(measured),"unique. Full passing, passed examples and denominator",[(a,v["pass1"],v["passed_examples"],v["examples"]) for a,v in totals.items()])
    print("file8-vs",pairs)
if __name__=="__main__":
    main()

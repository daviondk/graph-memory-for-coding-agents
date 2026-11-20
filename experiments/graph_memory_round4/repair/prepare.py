"""Build a past CI history and an argument-disjoint future test panel from two pinned public corpora."""
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import math
import re
from base import D,read,save,sha,stable,execute
from safe_ast import checked
from policy import mutations

def compatible(x):
    if isinstance(x,list):return len(x)<=160 and all(compatible(a) for a in x)
    if isinstance(x,dict):return all(isinstance(k,str) and compatible(v) for k,v in x.items())
    return type(x) in (str,int,float,bool,type(None)) and (not isinstance(x,(float,int)) or math.isfinite(x) and abs(x)<=2500)
def assertions(row):
    tr=ast.parse(row["test"])
    f=next(n for n in tr.body if isinstance(n,ast.FunctionDef) and n.name=="check")
    arg=f.args.args[0].arg
    result=[];all_args=[]
    for n in f.body:
        if not isinstance(n,ast.Assert):continue
        n.msg=None
        calls=[a for a in ast.walk(n.test) if isinstance(a,ast.Call) and isinstance(a.func,ast.Name) and a.func.id==arg]
        if len(calls)!=1 or calls[0].keywords:continue
        try:args=[ast.literal_eval(x) for x in calls[0].args]
        except (ValueError,TypeError):continue
        if any(args==a for a in all_args):continue
        all_args.append(args)
        if not compatible(args):continue
        calls[0].func.id=row["entry_point"]
        source=ast.unparse(n)
        if len(source.encode())>315:continue
        if {x.id for x in ast.walk(n) if isinstance(x,ast.Name)}-{row["entry_point"],"abs","round","len","sorted","sum","min","max","set","list","tuple","str","int","float","bool","all","any"}:continue
        try:checked(source)
        except (TypeError,SyntaxError,ValueError):continue
        result.append(source)
    return result,all_args
def future_examples(plus,seen,name):
    fn=next(n for n in ast.parse(plus).body if isinstance(n,ast.FunctionDef) and n.name=="check")
    assert ast.unparse(fn.body[-1]) in ["for i, (inp, exp) in enumerate(zip(inputs, results)):\n    assertion(candidate(*inp), exp, 0)","for i, (inp, exp) in enumerate(zip(inputs, results)):\n    assertion(candidate(*inp), exp, 1e-06)"],"nonstandard oracle"
    vals={x.targets[0].id:ast.literal_eval(x.value) for x in fn.body if isinstance(x,ast.Assign) and isinstance(x.targets[0],ast.Name) and x.targets[0].id in {"inputs","results"}}
    xs,ys=vals["inputs"],vals["results"]
    assert len(xs)==len(ys)
    tol=fn.body[-1].body[0].value.args[-1].value
    out=[];blocked=0
    for x,y in zip(xs,ys):
        if any(x==r for r in seen):blocked+=1;continue
        if not (compatible(x) and compatible(y)) or len(stable([x,y]).encode())>2400:continue
        if any(x==other[0] for other in out):continue
        out.append([x,y,tol])
    return sorted(out,key=lambda r:sha(name+"|future|"+stable(r[0])))[:64],blocked
BAD=re.compile(r"\b(?:exploit|malware|weapon|cryptograph\w*|vulnerabilit\w*|password|penetration|path traversal)\b",re.I)
def inputs(row,plus):
    i=row["task_id"];entry=row["entry_point"]
    if i in ("Python/0","Python/1","Python/2") or BAD.search(row["instruction"]+" "+row["signature"]):raise ValueError("scope_schema")
    raw=row["declaration"]+row["buggy_solution"];canonical=row["declaration"]+row["canonical_solution"]
    checked(raw);checked(canonical)
    if len(raw.encode())>5500 or row["test_setup"].strip():raise ValueError("interface limits")
    cards,seen=assertions(row);novel,overlap=future_examples(plus,seen,i)
    if len(cards)<3 or len(novel)<4:raise ValueError("insufficient observations")
    return dict(id=i,name=entry,source=raw,original=canonical,cards=cards,novel=novel,overlap=overlap)
def calibrate(t):
    panel=t["cards"]+t["novel"]
    jobs=[execute({"source":s,"name":t["name"],"examples":panel}) for s in [t["source"],t["original"]]]
    a,b=jobs
    if a.get("status")!="ok" or b.get("status")!="ok":return "runner calibration",jobs
    if not all(b["bits"]):return "reference did not pass",jobs
    if all(a["bits"][len(t["cards"]):]):return "bug passes new inputs",jobs
    return "admitted",jobs
def main():
    assert sha((D/"humanevalpack.parquet").read_bytes())=="ed5f15d789156e21222bfcD556c425a39042355c84ae1e8b058abd6a3d7f8075".lower()
    assert sha((D/"evalplus.jsonl.gz").read_bytes())==read("evalplus_source.json")["sha256"]
    plus={r["task_id"].split("/")[-1]:r for r in map(json.loads,gzip.open(D/"evalplus.jsonl.gz","rt",encoding="utf8"))}
    candidates=[];log={}
    for row in read("humanevalpack.json"):
        i=row["task_id"];plusrow=plus[i.split("/")[-1]]
        assert plusrow['entry_point']==row['entry_point']
        try:candidates.append(inputs(row,plusrow['test']))
        except (TypeError,ValueError,SyntaxError,AssertionError,KeyError,StopIteration,OverflowError) as exc:log[i]=str(exc)[:110] or type(exc).__name__
    candidates.sort(key=lambda t:sha("r4-registered|"+t["id"]))
    with ThreadPoolExecutor(6) as pool:controls=list(pool.map(calibrate,candidates))
    save("calibration.json.gz",{t["id"]:c for t,c in zip(candidates,controls)})
    selected=[]
    for t,(result,_) in zip(candidates,controls):
        log[t["id"]]=result
        if result=="admitted" and len(selected)<64:selected.append(t)
    assert selected
    save("screening.json",{"reasons":log,"counts":dict(Counter(log.values())),"selected":[t["id"] for t in selected]})
    save("past.json.gz",[{k:t[k] for k in ("id","name","source","cards")} for t in selected])
    save("future.json.gz",[{k:t[k] for k in ("id","name","original","novel","overlap")} for t in selected])
    print("screened",len(candidates),"selected",len(selected),"past",sum(len(t["cards"]) for t in selected),"new",sum(len(t["novel"]) for t in selected),flush=True)
if __name__=="__main__":main()


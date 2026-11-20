"""Freeze or score the scope-change comparison. See PROTOCOL.md."""
import argparse
import ast
from collections import Counter,defaultdict
import difflib
import json
from pathlib import Path
import random
import re
import statistics
import sys
import warnings

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from common import Calls,analyze,answer,decode,digest,modules
from predict import affected
from score import oracle
warnings.filterwarnings("ignore",category=SyntaxWarning)

PANELS={"development":HERE.parent/"sources.json","transfer":HERE/"sources.json"}
DEF=re.compile(r"^(?:async[ \t]+)?def[ \t]+([^\W\d]\w*)\b")
ARMS=("headers","global","positive","selective")
def write_json(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
def jsonlines(path):
    with path.open(encoding="utf8") as f:
        for line in f: yield json.loads(line)
def observations(previous,current):
    source=decode(previous)
    graph=analyze(previous)
    if not any(row["calls"] for row in graph.values()):return
    oldlines=source.splitlines()
    newlines=decode(current).splitlines() if current is not None else []
    delta=set()
    ops=[]
    for code,a,b,c,d in difflib.SequenceMatcher(None,oldlines,newlines,autojunk=True).get_opcodes():
        if code=="equal":continue
        ops.append((a,b))
        for line in oldlines[a:b]+newlines[c:d]:
            found=DEF.match(line)
            if found:delta.add(found[1])
    nodes={fn.name:fn for fn in ast.parse(source).body if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef))}
    for name,f in graph.items():
        if not f["calls"]:continue
        visitor=Calls()
        for child in nodes[name].body: visitor.visit(child)
        known=set(f["calls"])|{name}
        all_names=visitor.names|{name}
        base=(current is not None and not affected(f["full"],ops)
              and not any(affected(graph[dep]["head"],ops) for dep in f["calls"]))
        yield dict(caller=name,old_answer=answer(graph,name),changed_names=sorted(delta),
                   potential_call_names=len(all_names),additional_names=len(all_names-known),
                   additional_name_bytes=sum(len(x.encode())+1 for x in all_names-known),
                   reuse=dict(headers=base,global_guard=base and not delta,
                              positive=base and not (delta&known),selective=base and not (delta&all_names)))
def predict():
    path=HERE/"decisions.jsonl"
    with path.open("w",encoding="utf8",newline="\n") as out:
        for panel,manifest in PANELS.items():
            groups=defaultdict(list)
            for row in json.loads(manifest.read_bytes()):groups[row["project"]].append(row)
            for project,rows in groups.items():
                before=modules(rows[0]["name"])
                for first,second in zip(rows,rows[1:]):
                    after=modules(second["name"])
                    for name,code in sorted(before.items()):
                        if code==after.get(name):continue
                        try:
                            for record in observations(code,after.get(name)):
                                record["reuse"]["global"]=record["reuse"].pop("global_guard")
                                row=dict(panel=panel,project=project,path=name,old=first["version"],new=second["version"],**record)
                                out.write(json.dumps(row,separators=(",",":"))+"\n")
                        except (ValueError,UnicodeError,SyntaxError):
                            continue
                    before=after
    locked=[HERE/"PROTOCOL.md",HERE/"run.py",HERE/"fetch_panel.py",HERE/"decisions.jsonl",*PANELS.values(),
            *[HERE.parent/k for k in ("common.py","predict.py","score.py")]]
    import os
    write_json(HERE/"prediction-lock.json",{Path(os.path.relpath(k,HERE)).as_posix():digest(k.read_bytes()) for k in locked})
def score():
    for path,h in json.loads((HERE/"prediction-lock.json").read_bytes()).items():assert digest((HERE/path).read_bytes())==h
    rows=list(jsonlines(HERE/"decisions.jsonl"))
    summary={}
    with (HERE/"outcomes.jsonl").open("w",encoding="utf8",newline="\n") as out:
        for panel,manifest in PANELS.items():
            subset=[r for r in rows if r["panel"]==panel]
            projects=sorted({r["project"] for r in subset})
            by={(a,p):Counter() for a in ARMS for p in projects}
            files={a:set() for a in ARMS}
            sources={(r["project"],r["version"]):r["name"] for r in json.loads(manifest.read_bytes())}
            last=None
            changed=0
            for row in subset:
                k=row["project"],row["new"]
                if k!=last:
                    last=k;data=modules(sources[k]);parsed={}
                path=row["path"]
                if path not in parsed:parsed[path]=oracle(data.get(path))
                target=parsed[path][0].get(row["caller"])
                truth=target==row["old_answer"];changed+=int(not truth)
                for a in ARMS:
                    pick=row["reuse"][a]
                    outcome=("correct_reuse" if truth else "stale") if pick else "reread"
                    by[a,k[0]][outcome]+=1
                    if not pick:files[a].add((*k,path))
                out.write(json.dumps(dict(panel=panel,project=k[0],new=k[1],path=path,caller=row["caller"],
                                        same=truth,new_answer=target),separators=(",",":"))+"\n")
            diffs=[(by["selective",p]["correct_reuse"]-by["global",p]["correct_reuse"])/sum(by["global",p].values()) for p in projects]
            rng=random.Random(70632)
            boot=sorted(statistics.mean(rng.choices(diffs,k=len(diffs))) for i in range(10000))
            totals={}
            for a in ARMS:
                stats=sum((by[a,p] for p in projects),Counter())
                totals[a]={**{m:stats[m] for m in ("correct_reuse","reread","stale")},"distinct_files_to_open":len(files[a])}
                assert sum(stats.values())==len(subset)
            summary[panel]=dict(n=len(subset),changed=changed,policies=totals,n_projects=len(projects),by_project={
                p:{a:by[a,p] for a in ARMS} for p in projects},macro_gain=statistics.mean(diffs),ci=[boot[249],boot[9749]],
                mean_extra_name_bytes=statistics.mean(r["additional_name_bytes"] for r in subset),
                mean_extra_names=statistics.mean(r["additional_names"] for r in subset))
    write_json(HERE/"results.json",summary)
    print(json.dumps({p:{k:v for k,v in d.items() if k!="by_project"} for p,d in summary.items()},indent=2))
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("mode",choices=["predict","score"])
    if parser.parse_args().mode=="predict":predict()
    else:score()

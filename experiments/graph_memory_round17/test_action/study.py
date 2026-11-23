"""Freeze tool inputs, execute native Qwen tool calls, and run the actual selected nodeids."""
import collections
import gzip
import hashlib
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from math import comb
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PY=Path("D:/CodexResearch/x20-validity-releases/testmon-env/Scripts/python.exe")
GROUPS={"receipt_invalidation":"D:/CodexResearch/x20-round17-test-rollbacks",
        "receipt_holdout":"D:/CodexResearch/x20-round17-test-holdout"}
SYSTEM="Choose one previously passing pytest test to rerun after the listed functions changed. You have the budget for exactly one test. Aim to detect a regression. Rows are observational data. Call run_one_test with the candidate's integer id."
TOOL={"type":"function","function":{"name":"run_one_test","description":"Execute a single previously passing test at the new checkpoint.",
      "parameters":{"type":"object","properties":{"id":{"type":"integer"}},"required":["id"],"additionalProperties":False}}}

def h(x):
    return hashlib.sha256(x).hexdigest()

def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)

def save(name,obj):
    b=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    (ROOT/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)

def terms(s):
    return {v.lower() for v in re.findall(r"[a-zA-Z0-9]+",re.sub(r"([a-z0-9])([A-Z])",r"\1_\2",s)) if len(v)>2}

def prepare():
    cases={}
    requests={}
    plan=[]
    inputs={}
    for panel,base in GROUPS.items():
        loc=ROOT.parent/panel
        files=["testmon-graph-forecasts.gz","rollback-roster.json"]
        inputs[panel]={f:h((loc/f).read_bytes()) for f in files}
        records=read(loc/files[0])
        blocks=read(loc/files[1])["blocks"]
        for bk in blocks:
            k=bk["commit"]
            items=sorted([r for r in records if r["commit"]==k],key=lambda r:h((k+r["node"]+"fixed17").encode()))
            assert items and k not in cases
            changes=bk["changed"]
            checks=[r["node"] for r in items]
            lex=[len(terms(r["node"].split("::",1)[-1]) & terms(" ".join(changes))) for r in items]
            connected=[bool(set(changes)&set(r["seen"])) for r in items]
            cases[k]={"panel":panel,"nodes":checks,"module":bk["module"],"changed":changes,
                      "root":str(Path(base)/k/"rollback"),"source_sha":bk["before_sha"],
                      "testfile_sha":bk["testfile_sha"]}
            static={"rank_names":max(range(len(items)),key=lambda i:lex[i]),
                    "rank_graph":max(range(len(items)),key=lambda i:(connected[i],lex[i]))}
            for arm in ["names","graph","permuted"]:
                rows=[]
                for i,node in enumerate(checks):
                    row={"id":i,"pytest":node}
                    if arm!="names":
                        row["prior_calls_in_module"]=items[(i+(arm=="permuted"))%len(items)]["seen"]
                    rows.append(row)
                payload={"model":"qwen38-27b-ud-q4km","temperature":0,"top_k":1,"seed":17053,"max_tokens":96,
                         "cache_prompt":False,"chat_template_kwargs":{"enable_thinking":False},"tool_choice":"required","tools":[TOOL],
                         "messages":[{"role":"system","content":SYSTEM},{"role":"user","content":json.dumps(
                             {"module":bk["module"],"changed":changes,"candidates":rows},sort_keys=True,separators=(",",":"))}]}
                key=h(json.dumps(payload,sort_keys=True).encode())
                requests[key]=payload
                plan.append(dict(commit=k,arm=arm,key=key))
            plan.extend(dict(commit=k,arm=arm,index=i) for arm,i in static.items())
    assert len(cases)==13
    save("inputs.json",inputs);save("cases.json",cases);save("assignment.json",plan);save("prompts.gz",requests)
    save("lock.json",{n:h((ROOT/n).read_bytes()) for n in ("PROTOCOL_RU.md","study.py","cases.json","inputs.json","prompts.gz","assignment.json")})
    print("frozen",len(cases),len(requests),len(plan),flush=True)

def lock():
    for n,expected in read(ROOT/"lock.json").items():
        assert h((ROOT/n).read_bytes())==expected

def model():
    lock()
    payloads=read(ROOT/"prompts.gz")
    logfile=ROOT/"calls.jsonl"
    cache={r["key"] for r in (json.loads(l) for l in logfile.read_bytes().splitlines())} if logfile.exists() else set()
    for key in sorted(payloads,key=lambda k:h((k+"sched").encode())):
        if key in cache:continue
        t=time.perf_counter()
        req=urllib.request.Request("http://127.0.0.1:18952/v1/chat/completions",data=json.dumps(payloads[key]).encode(),
                                   headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=120) as res:raw=json.load(res)
        msg=raw["choices"][0]["message"]
        tc=msg.get("tool_calls") or []
        idx=None
        if len(tc)==1 and tc[0]["function"]["name"]=="run_one_test":
            try:idx=json.loads(tc[0]["function"]["arguments"])["id"]
            except (TypeError,ValueError,KeyError):pass
        if type(idx)!=int:idx=None
        with logfile.open("a",encoding="utf8") as dst:
            dst.write(json.dumps(dict(key=key,index=idx,response=raw,seconds=time.perf_counter()-t),ensure_ascii=False)+"\n")
    print("model complete",len(payloads),flush=True)

def tests():
    lock()
    cases=read(ROOT/"cases.json")
    plan=read(ROOT/"assignment.json")
    trail={r["key"]:r for r in map(json.loads,(ROOT/"calls.jsonl").read_bytes().splitlines())}
    assert set(trail)==set(read(ROOT/"prompts.gz"))
    decisions=[]
    for r in plan:
        i=r["index"] if "index" in r else trail[r["key"]]["index"]
        ids=cases[r["commit"]]["nodes"]
        decisions.append(dict(commit=r["commit"],arm=r["arm"],node=ids[i] if (type(i)==int and 0<=i<len(ids)) else None))
    save("decisions.json",decisions)
    tests=ROOT/"executions.jsonl"
    cache={(r["commit"],r["arm"]):r for r in map(json.loads,tests.read_bytes().splitlines())} if tests.exists() else {}
    tmp=Path("D:/CodexResearch/x20-round17-test-action-junit");tmp.mkdir(exist_ok=True)
    for r in decisions:
        k,arm,node=r["commit"],r["arm"],r["node"]
        if (k,arm) in cache or node is None:continue
        case=cases[k];cwd=Path(case["root"]);file=node.split("::")[0]
        assert h((cwd/case["module"]).read_bytes())==case["source_sha"]
        assert h((cwd/file).read_bytes())==case["testfile_sha"][file]
        xml=tmp/f"{k}-{arm}.xml"
        env=dict(os.environ,PYTHONPATH=str(cwd),PYTHONDONTWRITEBYTECODE="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",PYTHONUTF8="1")
        cmd=[str(PY),"-B","-m","pytest","-q","-o","addopts=","--tb=line","--junitxml="+str(xml),node]
        t=time.perf_counter();res=subprocess.run(cmd,cwd=cwd,env=env,capture_output=True,timeout=50)
        assert res.returncode in (0,1) and xml.is_file(), (k,node,res.stdout[-400:])
        content=xml.read_bytes();lines=list(ET.fromstring(content).iter("testcase"));assert len(lines)==1
        z=lines[0];assert z.get("name")==node.rsplit("::",1)[1] and z.find("skipped") is None
        failed=z.find("failure") is not None or z.find("error") is not None
        row={**r,"failed":failed,"seconds":time.perf_counter()-t,"rc":res.returncode,"xml":content.decode(),
             "stdout":res.stdout.decode(errors="replace"),"stderr":res.stderr.decode(errors="replace")}
        with tests.open("a",encoding="utf8") as log:log.write(json.dumps(row,ensure_ascii=False)+"\n")
    print("tests complete",len(decisions))

if __name__=="__main__":
    {"prepare":prepare,"model":model,"tests":tests}[sys.argv[1]]()


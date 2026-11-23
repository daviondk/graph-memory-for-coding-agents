"""Bounded implementation selection with local CPU inference and original executable graders."""
import ast
import collections
import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent
RT=Path(os.environ.get("PUBLIC_AUDIT_RUNTIME","D:/CodexResearch/x20-published-output-audit"))
REPO=RT/"agent-memory-bench"
MODEL=RT/"Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
BIN=Path(os.environ.get("LLAMA_SERVER","D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe"))
MODEL_DIG="3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597"
REV="c1b15726f1153b02dda0490ca1936bb86a809514"
TASK=("ts-casefold-sort","ts-crlf-export","ts-csv-quote","ts-dedup-order")
ARM=("none","matched","mismatched")
REFERENCE=("informed","naive")
PORT=19076
def sha(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()
def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()
def save(name,d):
    p=HERE/name
    b=(json.dumps(d,indent=2,sort_keys=True)+"\n").encode()
    if p.exists():
        assert p.read_bytes()==b,p
    else:
        p.write_bytes(b)
def python_script(path):
    a=ast.parse(path.read_text(encoding="utf8"))
    code=next(node.value.value for node in a.body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=="SCRIPT")
    body=ast.parse(code)
    for node in ast.walk(body):
        if isinstance(node,(ast.Module,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            if node.body and isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str):
                node.body.pop(0)
    return ast.unparse(body)
def experiment_cells():
    cells=[]
    for ix,t in enumerate(TASK):
        task=REPO/"tasks"/t
        text=json.loads((task/"task.json").read_bytes())["prompt"]
        options={k:python_script(task/"reference"/(k+".py")) for k in REFERENCE}
        for cond in ARM:
            other=TASK[(ix+1)%len(TASK)]
            mem="" if cond=="none" else (REPO/"tasks"/(t if cond=="matched" else other)/"precursors/p01/followup.txt").read_text(encoding="utf8").strip()
            for flip in (0,1):
                order=REFERENCE[::1 if flip==0 else -1]
                system="Select the Python implementation that best satisfies the task and any applicable repository-specific decision. A decision from a different context may be irrelevant. Return only one letter, A or B."
                prompt="Task\n"+text+"\n\nPrior decision\n"+(mem or "(no prior decision)")+"\n\nA\n"+options[order[0]]+"\n\nB\n"+options[order[1]]
                cells.append((digest(t+cond+str(flip)),t,cond,flip,order,system,prompt))
    return sorted(cells)
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
def check(t,kind):
    task=REPO/"tasks"/t
    checker=module(task/"checker.py","checker_"+t.replace("-","_"))
    ref=module(task/"reference"/(kind+".py"),"ref_"+kind+"_"+t.replace("-","_"))
    stage=RT/"check-stages"
    stage.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=stage) as td:
        cp=Path(td)/"work"
        shutil.copytree(task/"tree",cp)
        ref.apply(cp)
        ok,reason=checker.check(cp,REPO/"oracles"/t)
        return bool(ok),digest(str(reason))
def send(path,data=None,timeout=30):
    url=f"http://127.0.0.1:{PORT}"+path
    with urllib.request.urlopen(urllib.request.Request(url,data=None if data is None else json.dumps(data).encode(),headers={"Content-Type":"application/json"}),timeout=timeout) as r:
        return json.load(r)
def infer():
    assert subprocess.check_output(["git","-C",str(REPO),"rev-parse","HEAD"],text=True).strip()==REV
    assert sha(MODEL)==MODEL_DIG
    sys.path.insert(0,str(REPO))
    cells=experiment_cells()
    inputs={str(pp.relative_to(REPO)).replace("\\","/"):sha(pp) for t in TASK for pp in
          [REPO/"tasks"/t/"task.json",REPO/"tasks"/t/"precursors/p01/followup.txt",REPO/"tasks"/t/"checker.py"]+
             list((REPO/"tasks"/t/"reference").glob("*.py"))+list((REPO/"oracles"/t).rglob("*")) if pp.is_file()}
    save("downstream-plan.json",dict(protocol=sha(HERE/"DOWNSTREAM_PROTOCOL_RU.md"),revision=REV,model=MODEL_DIG,
                  inference_binary=sha(BIN),code=sha(Path(__file__)),sources=inputs,
                  tasks=[dict(key=key,t=t,arm=cond,swap=flip,request=digest(s+"\n"+u)) for key,t,cond,flip,order,s,u in cells]))
    env=dict(os.environ,CUDA_VISIBLE_DEVICES="-1",GGML_VK_VISIBLE_DEVICES="",PYTHONDONTWRITEBYTECODE="1")
    cmd=[str(BIN),"-m",str(MODEL),"--alias","qwen3-4b-instruct-2507","--host","127.0.0.1","--port",str(PORT),
        "--device","none","--n-gpu-layers","0","--jinja","--parallel","1","--ctx-size","4096",
        "--threads","4","--threads-batch","4","--batch-size","512","--ubatch-size","128","--cache-ram","0"]
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1",PORT))!=0
    with (RT/"cpu-native-server.log").open("wb") as log:
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        try:
            for _ in range(120):
                if proc.poll() is not None:
                    raise RuntimeError("dedicated server exited; see private log")
                try:
                    if send("/health",timeout=1)["status"]=="ok":
                        break
                except OSError:
                    pass
                time.sleep(1)
            else:
                raise TimeoutError("native server did not load")
            choices=[]
            for key,t,cond,flip,order,system,prompt in cells:
                logpath=RT/("decision-"+key+".json")
                req=dict(model="qwen3-4b-instruct-2507",messages=[dict(role="system",content=system),dict(role="user",content=prompt)],
                     temperature=0,seed=13,max_tokens=2,grammar='root ::= [AB]',stream=False)
                reqsha=digest(json.dumps(req,sort_keys=True))
                if logpath.exists():
                    ch=json.loads(logpath.read_bytes())
                    assert ch["request"]==reqsha and ch["model"]==MODEL_DIG
                else:
                    out=send("/v1/chat/completions",req,timeout=150)
                    answer=out["choices"][0]["message"]["content"].strip()
                    ch=dict(request=reqsha,model=MODEL_DIG,choice=answer,usage=out["usage"],finish=out["choices"][0]["finish_reason"])
                    logpath.write_text(json.dumps(ch),encoding="utf8")
                idx="AB".find(ch["choice"]) if ch["choice"] in ("A","B") else -1
                pick=order[idx] if idx!=-1 else None
                choices.append(dict(key=key,task=t,arm=cond,swap=flip,choice=ch["choice"],selected=pick,
                                        usage=ch["usage"],request=ch["request"],finish=ch["finish"]))
                print("native decision",len(choices),"/",len(cells),flush=True)
            save("downstream-decisions.json",choices)
        finally:
            if proc.poll() is None:
                proc.terminate()
            proc.wait(timeout=20)
    controls={}
    for t in TASK:
        controls[t]={a:check(t,a)[0] for a in REFERENCE}
    out=[]
    for ch in choices:
        ok,why=check(ch["task"],ch["selected"]) if ch["selected"] else (False,None)
        out.append(dict(key=ch["key"],task=ch["task"],arm=ch["arm"],swap=ch["swap"],passed=ok,checker_result_hash=why))
    save("downstream-results.json",dict(controls=controls,rows=out))
    print({a:sum(r["passed"] for r in out if r["arm"]==a) for a in ARM},controls,flush=True)
if __name__=="__main__":
    infer()

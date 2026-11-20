"""Isolate task copies on D, recover the two repository states and collect executable evidence."""
import concurrent.futures
import contextlib
import difflib
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parent
AGENT=ROOT.parents[1]/"graph_memory_round8"/"agent"
SCRATCH=Path("D:/CodexResearch/x20-round9-test311-runtime").resolve()
SCRATCH.mkdir(parents=True,exist_ok=True)
RUNS=ROOT/"runs"
RUNS.mkdir(exist_ok=True)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def read(p):
    return json.loads(p.read_bytes())


def save(p,data):
    p.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf8")


def patch(dir_,data):
    p=subprocess.run(["git","apply","--whitespace=nowarn","-"],cwd=dir_,env={**os.environ,"GIT_CEILING_DIRECTORIES":str(dir_.parent)},
                     input=data.encode(),capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace"))


def snapshot(root,paths):
    return {p:(root/p).read_text(encoding="utf8") if (root/p).is_file() else "" for p in paths}


def task(i):
    dest=RUNS/i
    dest.mkdir(exist_ok=True)
    origin=AGENT/"tasks"/i
    cfg=read(origin/"grading.json")
    control=read(origin/"grades_v2"/"control.json")
    nodes=sorted(set(x for v in control["base"]["tests"].values() for x in v["requested"]))
    save(dest/"nodes.json",nodes)
    paths=sorted(set(re.findall(r"(?m)^(?:--- a/|\+\+\+ b/)(sympy/[^\s]+)",cfg["patch"])))
    assert all(".." not in Path(p).parts for p in paths)
    with tempfile.TemporaryDirectory(prefix="task-",dir=SCRATCH) as tmp:
        root=Path(tmp).resolve()/"repo"
        assert root.is_relative_to(SCRATCH)
        shutil.copytree(origin/"base",root,ignore=shutil.ignore_patterns("__pycache__",".git",".pytest_cache","*.pyc"))
        patch(root,cfg["test_patch"])
        before=snapshot(root,paths)
        for side in ("base","gold"):
            if side=="gold":
                patch(root,cfg["patch"])
            cmd=[sys.executable,"-B",str(ROOT/"runstate.py"),str(dest/"nodes.json"),str(dest/(side+".json.gz"))]
            env={**os.environ,"PYTHONHASHSEED":"0","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1","PYTHONPATH":str(root)}
            with (dest/(side+".log")).open("wb") as log:
                p=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
            if p.returncode!=0:
                raise RuntimeError((i,side,p.returncode))
        after=snapshot(root,paths)
        payload=dict(before=before,after=after)
        (dest/"change.json.gz").write_bytes(gzip.compress(json.dumps(payload).encode(),mtime=0))
    print(i,len(nodes),flush=True)


def main():
    ids=sorted(read(AGENT/"assign.json"))
    inputs={f:digest((ROOT/f).read_bytes()) for f in ("PROTOCOL.md","runstate.py","collect.py")}
    sources={i:{f:digest((AGENT/"tasks"/i/f).read_bytes()) for f in ("grading.json","grades_v2/control.json")} for i in ids}
    save(ROOT/"collection-inputs.json",dict(scripts=inputs,sources=sources,ids=ids))
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        results={ex.submit(task,i):i for i in ids}
        errors={}
        for f in concurrent.futures.as_completed(results):
            if f.exception():
                errors[results[f]]=str(f.exception())
        save(ROOT/"collection-errors.json",errors)
        if errors:raise RuntimeError(errors)
if __name__=="__main__":
    main()


"""Rebuild test discovery in isolated snapshots without editing any logged checkout."""
import concurrent.futures
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
PYTHON=Path("D:/CodexResearch/x20-round9-test311-runtime/venv/Scripts/python.exe")
TEMP=Path("D:/CodexResearch/x20-round9-type-observations").resolve()
TEMP.mkdir(exist_ok=True)
PANELS={"testmemory_compat":WORK/"graph_memory_round8/agent","testmemory_holdout":WORK/"graph_memory_round7/reader"}


def apply(root,data):
    subprocess.run(["git","apply","--whitespace=nowarn","-"],cwd=root,input=data.encode(),
                 env={**os.environ,"GIT_CEILING_DIRECTORIES":str(root.parent)},check=True,capture_output=True)


def run_one(panel,i):
    old=PANELS[panel]/"tasks"/i
    cfg=json.loads((old/"grading.json").read_bytes())
    nodes=ROOT.parent/panel/"runs"/i/"nodes.json"
    requested=set(json.loads(nodes.read_bytes()))
    out=ROOT/panel/i
    out.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory(prefix="shape-",dir=TEMP) as tmp:
        path=Path(tmp).resolve()/"repo"
        assert path.is_relative_to(TEMP)
        shutil.copytree(old/"base",path,ignore=shutil.ignore_patterns(".git","__pycache__","*.pyc",".pytest_cache"))
        apply(path,cfg["test_patch"])
        for side in ("base","gold"):
            if side=="gold":apply(path,cfg["patch"])
            dest=out/(side+".json")
            with (out/(side+".log")).open("wb") as log:
                subprocess.run([str(PYTHON),"-B",str(ROOT/"observe.py"),str(nodes),str(dest)],cwd=path,
                    env={**os.environ,"PYTHONPATH":str(path),"PYTHONDONTWRITEBYTECODE":"1","PYTHONUTF8":"1",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONHASHSEED":"0"},check=True,timeout=120,stdout=log,stderr=subprocess.STDOUT)
            result=json.loads(dest.read_bytes())
            assert result["code"]==0 and set(result["records"])==requested,(panel,i,side,result["code"])
    return i


if __name__=="__main__":
    jobs=[(panel,i.name) for panel,p in PANELS.items() for i in sorted((p/"tasks").iterdir()) if i.is_dir() and (i/"grading.json").exists()]
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        for value in ex.map(lambda x:run_one(*x),jobs):print(value,flush=True)

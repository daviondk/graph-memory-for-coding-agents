"""Exercise the published testmon package without reusing a modified working tree."""
import concurrent.futures
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collect import AGENT,ROOT,RUNS,SCRATCH,digest,patch,read,save

PLUGIN=__import__("pathlib").Path("D:/CodexResearch/x20-round9-test311-runtime/testmon")
def task(i):
    origin=AGENT/"tasks"/i
    cfg=read(origin/"grading.json")
    out=RUNS/i
    with tempfile.TemporaryDirectory(prefix="testmon-",dir=SCRATCH) as tmp:
        root=__import__("pathlib").Path(tmp).resolve()/"repo"
        assert root.is_relative_to(SCRATCH)
        shutil.copytree(origin/"base",root,ignore=shutil.ignore_patterns("__pycache__",".pytest_cache",".git","*.pyc",".testmondata*"))
        patch(root,cfg["test_patch"])
        changed=set(__import__("re").findall(r"(?m)^(?:--- a/|\+\+\+ b/)(sympy/[^\s]+)",cfg["patch"]))
        base={p:((root/p).read_bytes() if (root/p).exists() else None) for p in changed}
        hashes={}
        for state in ("base_build","gold_select","gold_build","base_select"):
            if state=="gold_select":
                patch(root,cfg["patch"])
            if state=="gold_build":
                # The reverse direction gets its own fresh database.
                for db in root.glob(".testmondata*"):
                    assert db.is_file() and db.parent==root
                    db.unlink()
            if state=="base_select":
                for p,body in base.items():
                    f=root/p
                    if body is None:
                        if f.exists():f.unlink()
                    else:
                        f.write_bytes(body)
            if state in ("gold_select","base_select"):
                mark=time.time() + (5 if state=="gold_select" else 10)
                for p in changed:
                    if (root/p).exists():os.utime(root/p,(mark,mark))
            out_json=out/("testmon-"+state+".json")
            cmd=[sys.executable,"-B",str(ROOT/"testmon_runner.py"),str(out/"nodes.json"),str(out_json)]
            env={**os.environ,"PYTHONPATH":os.pathsep.join((str(PLUGIN),str(root))),"PYTHONDONTWRITEBYTECODE":"1",
                 "PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"}
            t=time.monotonic()
            with (out/("testmon-"+state+".log")).open("wb") as f:
                ret=subprocess.run(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
            if ret.returncode or not out_json.exists():
                raise RuntimeError((i,state,ret.returncode))
            data=read(out_json)
            data["wall_s"]=time.monotonic()-t
            save(out_json,data)
            hashes[state]=digest(out_json.read_bytes())
        save(out/"testmon-lock.json",hashes)
        print(i,flush=True)
if __name__=="__main__":
    ids=read(ROOT/"collection-inputs.json")["ids"]
    dist=next(d for d in importlib.metadata.distributions(path=[str(PLUGIN)]) if d.metadata["Name"].lower()=="pytest-testmon")
    save(ROOT/"testmon-input.json",dict(package=dist.metadata["Name"],version=dist.version,protocol=digest((ROOT/"TESTMON.md").read_bytes()),
        package_files={str(f):digest(dist.locate_file(f).read_bytes()) for f in dist.files if str(f).endswith(".py")}))
    with concurrent.futures.ThreadPoolExecutor(3) as executor:
        jobs={executor.submit(task,i):i for i in ids}
        errors={}
        for f in concurrent.futures.as_completed(jobs):
            if f.exception():errors[jobs[f]]=str(f.exception())
        save(ROOT/"testmon-errors.json",errors)
        if errors:raise RuntimeError(errors)

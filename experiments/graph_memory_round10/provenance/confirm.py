"""Physically rerun each identical test batch on both versions after locking schedules."""
from common import *
from concurrent.futures import ThreadPoolExecutor
import os,shutil,subprocess,tempfile
FOLDER=ROOT/"confirmations"
SCRATCH=ROOT/"tmp"
PY=Path("D:/CodexResearch/x20-round9-test311-runtime/venv/Scripts/python.exe")
def patch(wd,diff):
    subprocess.run(["git","apply","--whitespace=nowarn","-"],input=diff.encode(),cwd=wd,check=True,capture_output=True,
                   env={**os.environ,"GIT_CEILING_DIRECTORIES":str(wd.parent)})
def run(pair):
    records=sorted(pair,key=lambda r:r["direction"]);assert len(records)==2
    task=records[0]["task"];panel=records[0]["panel"]
    src=ORIG[panel]/"tasks"/task;cfg=get(src/"grading.json");target=FOLDER/task;target.mkdir(exist_ok=True)
    out={};nodes=[x["node"] for x in records[0]["items"]]
    assert all([x["node"] for x in r["items"]]==nodes for r in records)
    put(target/"nodes.json",nodes)
    with tempfile.TemporaryDirectory(prefix="workspace-",dir=SCRATCH) as temp:
        wd=Path(temp)/"repo"
        shutil.copytree(src/"base",wd,ignore=shutil.ignore_patterns("__pycache__",".git",".pytest_cache",".testmondata*","*.pyc"))
        patch(wd,cfg["test_patch"])
        for side,direction in (("base","revert"),("gold","fix")):
            rec=next(r for r in records if r["direction"]==direction)
            if side=="gold":patch(wd,cfg["patch"])
            pp=target/(side+".json");log=target/(side+".log")
            env={**os.environ,"PYTHONPATH":str(wd),"PYTHONHASHSEED":"0","PYTHONUTF8":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1",
                 "PYTHONDONTWRITEBYTECODE":"1","TEMP":str(SCRATCH),"TMP":str(SCRATCH)}
            with log.open("wb") as fp:
                subprocess.run([str(PY),"-B",str(ROOT/"pytest_runner.py"),str(target/"nodes.json"),str(pp)],cwd=wd,
                               env=env,stdout=fp,stderr=subprocess.STDOUT,timeout=240,check=True)
            packet=get(pp);ref=fh(pp)
            assert packet["code"] in (0,1) and set(packet["reports"])==set(nodes)
            out[rec["key"]]={node:dict(status=status(packet["reports"],node),source_ref=sha(packed([ref,node,packet["reports"][node]])),
                                     execution=pp.relative_to(ROOT).as_posix()) for node in nodes}
    print(task,len(nodes),flush=True)
    return out
def main():
    import importlib.metadata as md
    assert Path(sys.executable).resolve()==PY.resolve()
    snap={n:md.version(n) for n in ("pytest","coverage","pytest-testmon","py","mpmath")}
    assert sys.version_info[:3]==(3,11,15) and snap["py"]=="1.11.0" and snap["pytest"]=="7.4.4"
    lock=get(ROOT/"plan-lock.json");assert lock["plans"]==fh(ROOT/"plans.gz")
    FOLDER.mkdir(exist_ok=True);SCRATCH.mkdir(exist_ok=True)
    records=get(ROOT/"inputs.gz");tasks={}
    for r in records:tasks.setdefault(r["task"],[]).append(r)
    output={}
    with ThreadPoolExecutor(3) as ex:
        for x in ex.map(run,tasks.values()):output.update(x)
    put(ROOT/"fresh-results.gz",output)
    put(ROOT/"fresh-lock.json",dict(plans=fh(ROOT/"plans.gz"),data=fh(ROOT/"fresh-results.gz"),runtime=snap,python=sys.version,
              runners={n:fh(ROOT/n) for n in ("confirm.py","pytest_runner.py")},files={
              f.relative_to(ROOT).as_posix():fh(f) for f in sorted(FOLDER.rglob("*")) if f.is_file()}))
if __name__=="__main__":main()

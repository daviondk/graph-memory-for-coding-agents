from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import ast
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from plan19 import ROOT,old,old_select

ARMS=("all","previous","path","projected","projected_ast")
NAMES=("SCREEN_RU.md","PROTOCOL_RU.md","plan19.py","plan.json","observe.py","experiment.py")
READER=old.PY.parents[1]/"Lib/site-packages/_pytest/config/findpaths.py"
def lock():
    assert not (ROOT/"forecast-seal.json").exists()
    old.put(ROOT/"plan-seal.json",{**{n:old.sha((ROOT/n).read_bytes()) for n in NAMES},
        "r18_selector":old.sha((Path(old.__file__).parent/"forecast.py").read_bytes()),
        "r18_graph":old.sha((Path(old.__file__).parent/"owners.py").read_bytes())})
def check():
    for n,h in old.load(ROOT/"plan-seal.json").items():
        if n.startswith("r18_"):
            name={"r18_graph":"owners.py","r18_selector":"forecast.py"}[n];p=Path(old.__file__).parent/name
        else:p=ROOT/n
        assert old.sha(p.read_bytes())==h,n
def ast_equal(p):
    files=[]
    for f in p["modules"]:
        a=old.git("show",p["true_parent"]+":"+f);b=old.git("show",p["current"]+":"+f)
        if ast.dump(ast.parse(a))==ast.dump(ast.parse(b)):files.append(f)
    return files

def choices(p,test,clean,runtime):
    reasons={k:[] for k in ARMS}
    reasons["all"].append("run_all")
    if not clean:
        for k in ARMS[1:]:reasons[k].append("baseline_unknown")
        return reasons
    basic=old_select(p,test,runtime["trace"],clean)["outer_function"]
    if basic:reasons["previous"].append("previous_graph")
    for arm in ("path","projected","projected_ast"):
        modules=p["modules"]
        if arm=="projected_ast":modules={k:v for k,v in modules.items() if k not in p["ast_equal"]}
        active={**p,"modules":modules,"force_all":p["remaining_force_all"]}
        if old_select(active,test,runtime["trace"],clean)["outer_function"]:
            reasons[arm].append("remaining_global" if active["force_all"] else "changed_test" if test in p["edited_tests"] else "source_dependency")
        if runtime["subprocess_events"] or runtime["unknown"]:
            reasons[arm].append("opaque_child_or_path")
        for path,f in p["resources"].items():
            if f["mode"]!="M":
                reasons[arm].append("membership_changed:"+path);continue
            readers=set(runtime["resource_reads"][path])
            if f["kind"]=="toml":
                ok=f["before_projection"][0]=="parsed" and f["after_projection"][0]=="parsed"
                if not ok:reasons[arm].append("unknown_toml:"+path);continue
                projected=arm!="path" and readers=={"pytest_config"} and f["before_projection"]==f["after_projection"]
                if readers and not projected:reasons[arm].append("toml_observed:"+path)
            elif readers:reasons[arm].append("resource_observed:"+path)
    return reasons

def run(job):
    p,test,stage,archive,scratch=job
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        tmp=Path(tmp);repo=tmp/"src";repo.mkdir()
        with tarfile.open(archive,"r:") as a:a.extractall(repo,filter="data")
        sha=p["true_parent"] if stage=="base" else p["current"]
        assert old.sha((repo/test).read_bytes())==p["hashes"][stage][test]
        for f,m in p["modules"].items():
            assert old.sha((repo/f).read_bytes())==m["old_sha" if stage=="base" else "new_sha"]
        for f,m in p["resources"].items():
            expected=m["before_sha" if stage=="base" else "after_sha"]
            if expected is None:assert not (repo/f).exists()
            else:assert old.sha((repo/f).read_bytes())==expected
        config={"test":test,"out":str(tmp/"result.json"),"pytest_reader":str(READER),"resources":list(p["resources"]),
            "modules":list(p["modules"])}
        cfg=tmp/"cfg.json";old.put(cfg,config)
        env={**os.environ,"PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONHASHSEED":"0"}
        env.pop("PYTHONPATH",None);env.pop("PYTEST_ADDOPTS",None)
        start=time.perf_counter()
        try:
            pr=subprocess.run([str(old.PY),"-B",str(ROOT/"observe.py"),str(cfg)],cwd=repo,timeout=150,capture_output=True,env=env)
            rc=pr.returncode;log=pr.stdout+b"\n"+pr.stderr
            data=old.load(tmp/"result.json") if (tmp/"result.json").exists() else None
        except subprocess.TimeoutExpired as exc:
            rc="timeout";data=None;log=(exc.stdout or b"")+b"\n"+(exc.stderr or b"")
        run_secs=time.perf_counter()-start
        try:passed={n for n,h,k in data["phases"] if h=="call" and k=="passed"};failed={n for n,h,k in data["phases"] if k=="failed"}
        except TypeError:passed=set();failed=set()
        clean=bool(rc==0 and data and data["pytest_rc"]==0 and passed and not failed)
        row=dict(current=p["current"],base=p["true_parent"],sha=sha,panel=p["panel"],file=test,stage=stage,rc=rc,
            clean=clean,passed=len(passed),failed=len(failed),seconds=run_secs,results=data,log=log.decode(errors="replace"))
        if stage=="base":
            row["reasons"]=choices(p,test,clean,data)
            row["pred"]={a:bool(reasons) for a,reasons in row["reasons"].items()}
        return row

def execute(stage):
    check();plan=old.load(ROOT/"plan.json")
    assert old.sha(READER.read_bytes())==plan["pytest_findpaths_sha"]
    if stage=="current":
        seal=old.load(ROOT/"forecast-seal.json")
        assert all(old.sha((ROOT/n).read_bytes())==h for n,h in seal.items())
    start=time.perf_counter();rows=[]
    with tempfile.TemporaryDirectory(prefix="_run_",dir=ROOT) as tmp:
        scratch=Path(tmp);jobs=[]
        for p in plan["cohort"]+(plan["calibration"] if stage=="base" else []):
            commit=p["true_parent"] if stage=="base" else p["current"]
            ar=scratch/(commit+".tar")
            if not ar.exists():ar.write_bytes(old.git("archive","--format=tar",commit))
            p["ast_equal"]=ast_equal(p)
            p["hashes"]={"base":p["test_sha"],"current":{f:old.sha(old.git("show",p["current"]+":"+f)) for f in p["tests"]}}
            jobs.extend((p,f,stage,ar,scratch) for f in p["tests"])
        with ThreadPoolExecutor(max_workers=5) as pool:
            for row in pool.map(run,jobs):
                rows.append(row)
                if len(rows)%10==0:print("retained",stage,len(rows),"/",len(jobs),flush=True)
    name="forecasts.json.gz" if stage=="base" else "current-runs.json.gz"
    old.put(ROOT/name,rows)
    if stage=="base":
        old.put(ROOT/"forecast-seal.json",{n:old.sha((ROOT/n).read_bytes()) for n in ("plan-seal.json",name)})
    print("completed",stage,len(rows),"clean",sum(r["clean"] for r in rows),"wall",round(time.perf_counter()-start,2),flush=True)
if __name__=="__main__":
    if sys.argv[1]=="lock":lock()
    else:execute(sys.argv[1])

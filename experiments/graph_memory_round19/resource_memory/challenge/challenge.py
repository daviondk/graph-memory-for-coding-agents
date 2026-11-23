"""Synthetic mechanism tests with real files, instrumentation, subprocesses and pytest failures."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from plan19 import old,config_projection
from experiment import choices,READER

STUB="loguru/__init__.pyi";HELPER="tests/local_helper.py";CONF="pyproject.toml"
toml='[project]\nname = "small"\n[tool.pytest.ini_options]\nfilterwarnings = ["default"]\n[tool.ruff]\nline-length = 88\n'
stub="CONST = 1\n"
helper='def get_value():\n    return "old"\n'
original={CONF:toml,STUB:stub,HELPER:helper}
tests={
    "plain":"def test_case():\n    assert 2 + 2 == 4\n",
    "raw_toml":'import tomllib\nfrom pathlib import Path\ndef test_case():\n    assert tomllib.loads(Path("pyproject.toml").read_text())["project"]["name"] == "small"\n',
    "warning":'import warnings\ndef test_case():\n    warnings.warn("marker", UserWarning)\n',
    "open_stub":'from pathlib import Path\ndef test_case():\n    assert Path("loguru/__init__.pyi").read_text() == "CONST = 1\\n"\n',
    "stat_stub":'from pathlib import Path\ndef test_case():\n    assert Path("loguru/__init__.pyi").stat().st_size == 10\n',
    "child_stub":'import subprocess,sys\ndef test_case():\n    printout = subprocess.check_output([sys.executable,"-c","from pathlib import Path; print(Path(\'loguru/__init__.pyi\').read_text().strip())"],text=True)\n    assert printout.strip() == "CONST = 1"\n',
    "helper":'from tests.local_helper import get_value\ndef test_case():\n    assert get_value() == "old"\n'}
mutations={"lint_only":(CONF,toml.replace("88","89")),"raw_name":(CONF,toml.replace("small","tall")),
    "pytest_warning":(CONF,toml.replace("default","error")),"stub_size_and_text":(STUB,"CONST = 12\n"),
    "helper_value":(HELPER,helper.replace("old","new"))}
def one(job):
    mutation,name,which,stage,scratch=job
    path,updated=mutations[mutation]
    with tempfile.TemporaryDirectory(dir=scratch) as temp:
        temp=Path(temp);repo=temp/"src";repo.mkdir()
        src={**original,"tests/__init__.py":"","loguru/__init__.py":"","tests/test_"+name+".py":"import loguru\n"+tests[name]}
        if stage=="current":src[path]=updated
        for file,text in src.items():
            dest=repo/file;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(text.encode("utf8"))
        test="tests/test_"+name+".py";config=temp/"cfg.json";out=temp/"runtime.json"
        old.put(config,{"test":test,"out":str(out),"resources":[path],"modules":[],"pytest_reader":str(READER)})
        env={**os.environ,"PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1"}
        env.pop("PYTEST_ADDOPTS",None);env.pop("PYTHONPATH",None)
        start=time.perf_counter()
        pr=subprocess.run([str(old.PY),"-B",str(ROOT.parent/"observe.py"),str(config)],cwd=repo,capture_output=True,env=env,timeout=30)
        runtime=old.load(out) if out.is_file() else None
        assert runtime is not None and pr.returncode==0
        passed=any(st=="passed" and ph=="call" for n,ph,st in runtime["phases"])
        clean=runtime["pytest_rc"]==0 and passed and not any(st=="failed" for n,ph,st in runtime["phases"])
        r={"mutation":mutation,"file":test,"stage":stage,"clean":clean,"seconds":time.perf_counter()-start,
            "old_sha":old.sha(original[path].encode()),"new_sha":old.sha(updated.encode()),"runtime":runtime,"log":(pr.stdout+b"\n"+pr.stderr).decode(errors="replace")}
        if stage=="base":
            resource={"kind":{STUB:"stub",HELPER:"helper",CONF:"toml"}[path],"mode":"M"}
            if path==CONF:resource.update(before_projection=config_projection(original[path].encode()),after_projection=config_projection(updated.encode()))
            p={"resources":{path:resource},"force_all":[["M",path]],"remaining_force_all":[],"modules":{},"ast_equal":[],"edited_tests":[]}
            r["reasons"]=choices(p,test,clean,runtime)
            r["pred"]={k:bool(v) for k,v in r["reasons"].items()}
        return r
def main():
    old.put(ROOT/"plan-seal.json",{p.name:old.sha(p.read_bytes()) for p in (ROOT/"PROTOCOL_RU.md",Path(__file__))})
    with tempfile.TemporaryDirectory(dir=ROOT) as scratch:
        with ThreadPoolExecutor(max_workers=5) as pool:
            base=list(pool.map(one,[(m,t,path,"base",scratch) for m,(path,_) in mutations.items() for t in tests]))
            old.put(ROOT/"base.json.gz",base);old.put(ROOT/"forecast-seal.json",{n:old.sha((ROOT/n).read_bytes()) for n in ("base.json.gz","plan-seal.json")})
            current=list(pool.map(one,[(m,t,path,"current",scratch) for m,(path,_) in mutations.items() for t in tests]))
            old.put(ROOT/"current.json.gz",current)
    observed=[]
    for b,c in zip(base,current,strict=True):
        assert (b["mutation"],b["file"])==(c["mutation"],c["file"]) and b["clean"] and b["old_sha"]!=b["new_sha"]
        nodes={(n,ph):st for n,ph,st in b["runtime"]["phases"]};after={(n,ph):st for n,ph,st in c["runtime"]["phases"]}
        assert nodes.keys()==after.keys()
        fail=any(before=="passed" and after[k]=="failed" for k,before in nodes.items())
        observed.append({"mutation":b["mutation"],"file":b["file"],"pred":b["pred"],"failed":fail})
    out={"cases":observed,"arms":{k:{"checked":sum(r["pred"][k] for r in observed),"caught":sum(r["failed"] and r["pred"][k] for r in observed),
        "misses":[(r["mutation"],r["file"]) for r in observed if r["failed"] and not r["pred"][k]]} for k in observed[0]["pred"]},
        "fail_count":sum(r["failed"] for r in observed)}
    old.put(ROOT/"results.json",out);print(out["fail_count"],out["arms"])
if __name__=="__main__":main()

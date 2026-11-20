"""Separate mechanism check for a file absent from all source traces before its creation."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from collect import ROOT,SCRATCH,digest,save
from predict import keys_for_change,observed,status,unpack

DIRECT="sympy/rules.py"; OPTIONAL="sympy/adjustments.py"
RULES="""try:
    from .adjustments import adjust
except ModuleNotFoundError:
    def adjust(amount):
        return amount + 1

def total(amount):
    return adjust(amount)
"""
IMPL="def adjust(amount):\n    return amount + 2\n"
NODE="tests/test_rules.py::test_total"
OUT=ROOT/"absence_audit";OUT.mkdir(exist_ok=True)
def call(root,out,script,tag,target):
    env={**os.environ,"PYTHONPATH":os.pathsep.join([str(SCRATCH/"testmon"),str(root)]),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONDONTWRITEBYTECODE":"1","PYTHONHASHSEED":"0","PYTHONUTF8":"1"}
    p=subprocess.run([sys.executable,"-B",str(ROOT/script),str(out/"nodes.json"),str(target)],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
    (out/(tag+".log")).write_bytes(p.stdout);assert p.returncode==0,(tag,p.stdout[-400:])
def scenario(direction):
    out=OUT/direction;out.mkdir(exist_ok=True);save(out/"nodes.json",[NODE])
    with tempfile.TemporaryDirectory(prefix="absence-",dir=SCRATCH) as t:
        root=Path(t).resolve();(root/"sympy").mkdir();(root/"tests").mkdir()
        sources={"sympy/__init__.py":"","sympy/rules.py":RULES,"tests/test_rules.py":"from sympy.rules import total\n\ndef test_total():\n    assert total(3) == 4\n"}
        for path,s in sources.items():(root/path).write_text(s,encoding="utf8")
        old,new=("","added") if direction=="create" else ("added","")
        candidate=root/OPTIONAL
        def setstate(flag):
            if flag:candidate.write_text(IMPL,encoding="utf8");os.utime(candidate,(1700000090,1700000090))
            else:candidate.unlink(missing_ok=True)
        setstate(old)
        call(root,out,"runstate.py","old",out/"old.json.gz")
        call(root,out,"testmon_runner.py","build",out/"build.json")
        setstate(new)
        call(root,out,"testmon_runner.py","select",out/"select.json")
        call(root,out,"runstate.py","new",out/"new.json.gz")
        before=unpack(out/"old.json.gz");after=unpack(out/"new.json.gz")
        touched,_=keys_for_change({OPTIONAL:IMPL if old else ""},{OPTIONAL:IMPL if new else ""})
        edges=observed("synthetic","old",{**sources,OPTIONAL:IMPL if old else ""},before["contexts"])
        selected=json.loads((out/"select.json").read_bytes())["reports"]
        return {"direction":direction,"old":status(before["reports"][NODE]),"new":status(after["reports"][NODE]),"touched":sorted(touched),
                "old_local_dependencies":sorted(edges[NODE]),"old_shared_dependencies":sorted(edges["shared"]),
                "exact_selected":bool(touched&(edges[NODE]|edges["shared"])),"testmon_selected":NODE in selected,
                "input_hashes":{k:digest(v.encode()) for k,v in {**sources,OPTIONAL:IMPL}.items()}}
if __name__=="__main__":
    rows=[scenario(d) for d in ["create","delete"]]
    assert [(v["old"],v["new"]) for v in rows]==[("passed","failed"),("failed","passed")]
    save(OUT/"results.json",rows);print([(r["direction"],r["exact_selected"],r["testmon_selected"]) for r in rows])

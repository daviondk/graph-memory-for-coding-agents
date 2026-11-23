"""Execute synthetic API contracts over an authentic production-code rollback with an original CLI comparator."""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as E
from pathlib import Path

ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT.parent/"receipt_invalidation"))
from rollback import build,read,sha,source
PY=Path("D:/CodexResearch/x20-binding-testmon-current/Scripts/python.exe")
COMMIT="0d74505531b3b10279f8e18572ba6857b2748936"
def put(n,v):
    b=json.dumps(v,sort_keys=True,ensure_ascii=False).encode()
    (ROOT/n).write_bytes(gzip.compress(b,mtime=0) if n.endswith(".gz") else b)
def call(cwd,stage,nodes,args):
    folder=cwd.parent/stage;folder.mkdir()
    xml=folder/"output.xml";edges=folder/"edges.json"
    cmd=[PY,"-B","-m","pytest","-q","-o","addopts=","--tb=short","--junitxml="+str(xml),*args,*nodes]
    out=subprocess.run(cmd,cwd=cwd,env={**os.environ,"PYTHONUTF8":"1","PYTHONDONTWRITEBYTECODE":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1","PYTHONPATH":str(ROOT),"REFLECTION_EDGES":str(edges)},capture_output=True,timeout=45)
    log=out.stdout.decode(errors="replace")+"\n"+out.stderr.decode(errors="replace")
    assert out.returncode in (0,1,5) and xml.exists(),log[-2400:]
    xmltext=xml.read_text(encoding="utf8")
    result={"test_contracts.py::"+c.get("name"):"fail" if c.find("failure") is not None or c.find("error") is not None else "skip" if c.find("skipped") is not None else "pass" for c in E.fromstring(xmltext).iter("testcase")}
    return {"outcomes":result,"edges":json.loads(edges.read_bytes()) if edges.exists() else None,"rc":out.returncode,"junit":xmltext,"log":log}
def main():
    names=["keyword_dispatch","direct_signature","indirect_signature","attribute_defaults","other_in_same_module","other_module"];nodes=["test_contracts.py::test_"+n for n in names]
    put("assignment.json",{"nodes":nodes,"hashes":{f:sha((ROOT/f).read_bytes()) for f in ("contracts.py","PROTOCOL_RU.md","control.py","reflection_plugin.py")},"commit":COMMIT})
    b=next(v for v in read(ROOT.parent/"receipt_invalidation/rollback-roster.json")["blocks"] if v["commit"]==COMMIT)
    cache=Path("D:/CodexResearch/x20-round17-testmon-stock");cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as t:
        cwd=Path(t)/"work";build(b,cwd);shutil.copyfile(ROOT/"contracts.py",cwd/"test_contracts.py")
        tm=["-p","testmon.pytest_testmon","--testmon","--testmon-forceselect"]
        warm=call(cwd,"graph",nodes,["-p","reflection_plugin"])
        warm_tm=call(cwd,"testmon",nodes,tm)
        unchanged=call(cwd,"unchanged",nodes,tm)
        assert list(warm["outcomes"].values()).count("pass")==6 and warm_tm["outcomes"]==warm["outcomes"] and not unchanged["outcomes"]
        changes={(b["module"],n) for n in b["changed"]}
        edges=warm["edges"]
        schedule={arm:[n for n in nodes if changes&{tuple(e) for kind in cols for e in edges[n][kind]}] for arm,cols in {"calls":["called"],"reflective":["called","signature"]}.items()}
        put("sealed-edges.json",{"schedule":schedule,"edges":edges,"hashes":{"assignment.json":sha((ROOT/"assignment.json").read_bytes())}})
        (cwd/b["module"]).write_bytes(source(b["parent"],b["module"]));assert sha((cwd/b["module"]).read_bytes())==b["before_sha"]
        full=call(cwd,"full",nodes,[]);tm_run=call(cwd,"tm-after",nodes,tm)
        actions={arm:call(cwd,arm,ids,[]) for arm,ids in schedule.items()}
        raw={"initial_graph":warm,"initial_testmon":warm_tm,"unchanged":unchanged,"full":full,"native":tm_run,"actions":actions}
        put("runs.gz",raw)
        score={}
        fail={n for n,v in full["outcomes"].items() if v=="fail"}
        for arm,r in {**actions,"testmon231":tm_run}.items():
            checked=set(r["outcomes"])
            assert all(full["outcomes"][k]==v for k,v in r["outcomes"].items())
            score[arm]={"checked":sorted(checked),"caught":sorted(checked&fail),"false_pass":sorted(fail-checked)}
        put("results.json",{"full":full["outcomes"],"arms":score})
        print({k:(len(v["checked"]),len(v["caught"]),len(v["false_pass"])) for k,v in score.items()},full["outcomes"])
if __name__=="__main__":main()

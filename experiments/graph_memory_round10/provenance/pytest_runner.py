"""Neutral observer of the actual local test run; never reads gold status."""
from pathlib import Path
import json,platform,sys,time
import pytest
cwd=Path.cwd()
sys.path.insert(0,str(cwd))
inp,out=map(Path,sys.argv[1:3])
nodes=json.loads(inp.read_bytes());reports={}
class Observe:
    def pytest_runtest_logreport(self,report):
        reports.setdefault(report.nodeid,[]).append([report.when,report.outcome,report.duration])
start=time.monotonic()
code=pytest.main(["-q","--disable-warnings","--tb=line","-o","addopts=",*nodes],plugins=[Observe()])
mod=sys.modules.get("sympy");assert mod is not None and Path(mod.__file__).resolve().is_relative_to(cwd)
out.write_text(json.dumps(dict(code=int(code),reports=reports,wall=time.monotonic()-start,python=platform.python_version(),
                               pytest=pytest.__version__),indent=1)+"\n",encoding="utf8")

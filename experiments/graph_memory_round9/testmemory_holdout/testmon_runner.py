"""Collect the actual node IDs executed by pytest-testmon on an isolated checkout."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path.cwd()))
nodes=json.loads(Path(sys.argv[1]).read_bytes())
records={}
class Observe:
    def pytest_runtest_logreport(self,report):
        records.setdefault(report.nodeid,[]).append([report.when,report.outcome,report.duration])
code=pytest.main(["-p","testmon.pytest_testmon","--testmon","--testmon-forceselect","-q","-o","addopts=",
                  "--tb=line","--disable-warnings",*nodes],plugins=[Observe()])
files={p.name:p.stat().st_size for p in Path.cwd().glob(".testmondata*") if p.is_file()}
Path(sys.argv[2]).write_text(json.dumps(dict(code=int(code),reports=records,db_bytes=files))+"\n",encoding="utf8")

import json,sys
from pathlib import Path
import importlib.metadata as md
import pytest
root=Path.cwd().resolve()
sys.path.insert(0,str(root/"vendor"));sys.path.insert(0,str(root))
observed={}
class Seen:
    def pytest_runtest_logreport(self,report):
        if report.when=="call":observed[report.nodeid]=report.outcome
rc=pytest.main(["-p","testmon.pytest_testmon","--testmon","--testmon-forceselect","-q","--disable-warnings","--tb=short","test_application.py"],plugins=[Seen()])
info=sorted([[(d.metadata["Name"] or "").lower(),d.version] for d in md.distributions(path=[str(root/"vendor")])])
Path(sys.argv[1]).write_text(json.dumps(dict(rc=int(rc),executed=observed,package_metadata=info,db_bytes=sum(p.stat().st_size for p in root.glob(".testmondata*")))),encoding="utf8")

"""Observe line and call events during one genuine parent-revision pytest run."""
import json
import os
from pathlib import Path
import sys
import threading
import time

def main():
    config=json.loads(Path(sys.argv[1]).read_bytes())
    repo=Path.cwd().resolve();out=Path(config["out"])
    wanted={os.path.normcase(str((repo/p).resolve())):p for p in config["paths"]}
    stats={p:{"calls":set(),"lines":set()} for p in wanted.values()}
    def trace(frame,event,arg):
        if event=="call":
            path=wanted.get(os.path.normcase(frame.f_code.co_filename))
            if path is None:return None
            stats[path]["calls"].add(frame.f_code.co_qualname.replace(".<locals>.","."))
        elif event=="line":
            path=wanted.get(os.path.normcase(frame.f_code.co_filename))
            if path:stats[path]["lines"].add(frame.f_lineno)
        return trace
    sys.path.insert(0,str(repo));sys.settrace(trace)
    import pytest
    outcomes=[]
    class Capture:
        def pytest_runtest_logreport(self,report):
            outcomes.append((report.nodeid,report.when,report.outcome))
    start=time.perf_counter()
    try:code=pytest.main(["-q","-o","addopts=","-p","no:cacheprovider",config["test"]],plugins=[Capture()])
    finally:sys.settrace(None)
    actual=Path(sys.modules["loguru"].__file__).resolve()
    assert actual.is_relative_to(repo)
    data={"pytest_rc":int(code),"elapsed_test_s":time.perf_counter()-start,"import_path":str(actual),"outcomes":outcomes,
          "trace":{p:{k:sorted(v) for k,v in s.items()} for p,s in stats.items()}}
    out.write_text(json.dumps(data,sort_keys=True),encoding="utf8")
if __name__=="__main__":main()

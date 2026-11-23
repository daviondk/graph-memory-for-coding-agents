"""Record real pytest node IDs, outcomes, and optional per-test function evidence."""
import json
import os
import sys
from pathlib import Path

import pytest

ROWS={}
ROOT=Path.cwd().resolve().as_posix().lower()+"/"
CAN_TRACE=os.environ.get("R17_TRACE")=="1"

@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_protocol(item,nextitem):
    key=item.nodeid.replace("\\","/")
    info=ROWS.setdefault(key,{"phases":{},"calls":[]})
    seen=set()
    def observe(frame,event,arg):
        if event!="call":return
        code=frame.f_code;file=code.co_filename.replace("\\","/")
        if not file.lower().startswith(ROOT) or "/more_itertools/" not in file:return
        relative="more_itertools/"+file.split("/more_itertools/")[-1]
        seen.add((relative,code.co_qualname.split(".")[0]))
    previous=sys.getprofile()
    if CAN_TRACE:sys.setprofile(observe)
    try:yield
    finally:
        if CAN_TRACE:sys.setprofile(previous)
        info["calls"]=sorted(seen)

def pytest_runtest_logreport(report):
    info=ROWS.setdefault(report.nodeid.replace("\\","/"),{"phases":{},"calls":[]})
    info["phases"][report.when]=report.outcome

def pytest_sessionfinish(session,exitstatus):
    Path(os.environ["R17_REPORT"]).write_text(json.dumps({"status":exitstatus,"rows":ROWS}),encoding="utf8")

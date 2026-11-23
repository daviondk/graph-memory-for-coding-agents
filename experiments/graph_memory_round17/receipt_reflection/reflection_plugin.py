"""Observe ordinary function entries and native inspect.signature first-argument object identity per test."""
import inspect
import json
import os
import sys
from pathlib import Path
import pytest

SEEN={}
ROOT=Path.cwd().as_posix().lower()+"/"
@pytest.hookimpl(hookwrapper=True,tryfirst=True)
def pytest_runtest_protocol(item,nextitem):
    executed=set();inspected=set()
    def profile(frame,event,args):
        if event!="call":return
        c=frame.f_code;file=c.co_filename.replace("\\","/")
        if file.lower().startswith(ROOT) and "/more_itertools/" in file:
            executed.add(("more_itertools/"+file.split("/more_itertools/")[-1],c.co_qualname.split(".")[0]))
        if c is inspect.signature.__code__:
            obj=frame.f_locals.get("obj")
            if inspect.isfunction(obj):
                path=obj.__code__.co_filename.replace("\\","/")
                if path.lower().startswith(ROOT) and "/more_itertools/" in path:
                    inspected.add(("more_itertools/"+path.split("/more_itertools/")[-1],obj.__qualname__.split(".")[0]))
    was=sys.getprofile();sys.setprofile(profile)
    try:yield
    finally:
        sys.setprofile(was)
        SEEN[item.nodeid]={"called":sorted(executed),"signature":sorted(inspected)}
def pytest_sessionfinish(session,exitstatus):
    Path(os.environ["REFLECTION_EDGES"]).write_text(json.dumps(SEEN,sort_keys=True),encoding="utf8")

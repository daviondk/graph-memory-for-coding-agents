"""Begin collection before pytest might import the library for its own console."""
import json
import os
import sys
from pathlib import Path

BASE = Path.cwd()
TARGET = (BASE/"colorama/ansi.py").as_posix().lower()
PREFIX = (BASE/"colorama").as_posix().lower() + "/"
ACTIVE = None
CALLS, TESTS, OUTCOMES = {}, {}, {}
TRACE = os.environ.get("COLOR_TRACE")=="1"


def observe(frame,event,arg):
    if event!="call":
        return
    loc = frame.f_code.co_filename.replace("\\","/").lower()
    if not loc.startswith(PREFIX):
        return
    root = frame.f_code.co_qualname.split(".")[0]
    if ACTIVE:
        evidence = TESTS[ACTIVE]
        if loc == TARGET:
            evidence["functions"].add(root)
            evidence["names"].update(frame.f_code.co_names)
        module = sys.modules.get("colorama.ansi")
        if module:
            reverse = {id(value): key for key,value in vars(module).items()
                       if key in ("Fore","Back","Style","Cursor") or callable(value)}
            for name in frame.f_code.co_names:
                if name in frame.f_globals and id(frame.f_globals[name]) in reverse:
                    evidence["names"].add(reverse[id(frame.f_globals[name])])
    elif loc == TARGET and root != "<module>":
        origin=frame.f_back
        while origin and not (origin.f_code.co_name=="<module>" and origin.f_code.co_filename.replace("\\","/").lower()==TARGET):
            origin=origin.f_back
        if origin:
            CALLS.setdefault(origin.f_lineno,set()).add(root)


if TRACE:
    sys.setprofile(observe)
import pytest


class Observer:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self,item,nextitem):
        global ACTIVE
        ACTIVE=item.nodeid
        TESTS[item.nodeid]={"functions":set(),"names":set()}
        try:
            yield
        finally:
            ACTIVE=None

    def pytest_runtest_logreport(self,report):
        OUTCOMES.setdefault(report.nodeid,{})[report.when]=report.outcome


status=pytest.main(sys.argv[1:],plugins=[Observer()])
sys.setprofile(None)
module = sys.modules["colorama.ansi"]
assert Path(module.__file__).resolve() == BASE/"colorama/ansi.py"
Path(os.environ["COLOR_OUT"]).write_text(json.dumps({
    "rc":int(status),"location":module.__file__,
    "import_calls":{str(k):sorted(v) for k,v in CALLS.items()},
    "tests":{k:{q:sorted(v) for q,v in vv.items()} for k,vv in TESTS.items()},"outcomes":OUTCOMES},sort_keys=True),encoding="utf8")
sys.exit(int(status))


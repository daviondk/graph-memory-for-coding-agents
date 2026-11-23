"""Collect import-time calls and per-test execution without accessing outcomes during prediction."""
import ast
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path.cwd()
LIB = ROOT / "example_library.py"
MODULE = LIB.as_posix().lower()
TRACE = os.environ.get("BIND_TRACE") == "1"
IMPORT_CALLS = {}
TESTS = {}
STATUS = {}
ACTIVE = None


def observe(frame,event,arg):
    if event != "call" or frame.f_code.co_filename.replace("\\","/").lower() != MODULE:
        return
    name = frame.f_code.co_qualname.split(".")[0]
    if name == "<module>":
        return
    if ACTIVE:
        row = TESTS[ACTIVE]
        row["functions"].add(name)
        row["names"].update(frame.f_code.co_names)
    else:
        origin = frame.f_back
        while origin and not (origin.f_code.co_name == "<module>" and
                              origin.f_code.co_filename.replace("\\","/").lower()==MODULE):
            origin = origin.f_back
        if origin:
            IMPORT_CALLS.setdefault(origin.f_lineno,set()).add(name)


def pytest_sessionstart(session):
    if TRACE:
        sys.setprofile(observe)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    global ACTIVE
    ACTIVE = item.nodeid
    TESTS[ACTIVE] = {"functions":set(),"names":set()}
    try:
        yield
    finally:
        ACTIVE = None


def pytest_runtest_logreport(report):
    STATUS.setdefault(report.nodeid,{})[report.when] = report.outcome


def pytest_sessionfinish(session,exitstatus):
    if TRACE:
        sys.setprofile(None)
    records = {k:{kind:sorted(v) for kind,v in value.items()} for k,value in TESTS.items()}
    data = {"tests":records,"import_calls":{str(n):sorted(v) for n,v in IMPORT_CALLS.items()},
            "outcomes":STATUS,"exitstatus":int(exitstatus)}
    Path(os.environ["BIND_OUT"]).write_text(json.dumps(data,sort_keys=True),encoding="utf8")


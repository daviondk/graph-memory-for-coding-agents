"""Collect import-time and test-time bindings without a list of project exports."""
import collections
import json
import os
import sys
from pathlib import Path

BASE = Path.cwd().resolve()
TARGET = (BASE / os.environ["AUTO_CHANGED_FILE"]).resolve()
MODULE = ".".join(TARGET.relative_to(BASE).with_suffix("").parts)
PACKAGE = (BASE / TARGET.relative_to(BASE).parts[0]).as_posix().casefold() + "/"
TARGET_NAME = TARGET.as_posix().casefold()
ACTIVE = None
call_lines = collections.defaultdict(set)
observations = {}
outcomes = {}


def exports(module):
    return {name:value for name,value in vars(module).items() if not name.startswith("__")}


def profile(frame, event, _arg):
    if event != "call":
        return
    filename = frame.f_code.co_filename.replace("\\", "/").casefold()
    if not filename.startswith(PACKAGE):
        return
    function = frame.f_code.co_qualname.split(".")[0]
    if ACTIVE is None:
        if filename == TARGET_NAME and function != "<module>":
            origin = frame.f_back
            while origin and not (origin.f_code.co_name == "<module>" and origin.f_code.co_filename.replace("\\","/").casefold() == TARGET_NAME):
                origin = origin.f_back
            if origin:
                call_lines[origin.f_lineno].add(function)
        return
    sample = observations[ACTIVE]
    if filename == TARGET_NAME:
        sample["functions"].add(function)
        sample["names"].update(frame.f_code.co_names)
    target = sys.modules.get(MODULE)
    if target is None:
        return
    reverse = collections.defaultdict(set)
    for key,value in exports(target).items():
        reverse[id(value)].add(key)
    for name in frame.f_code.co_names:
        if name in frame.f_globals:
            aliases = reverse.get(id(frame.f_globals[name]), ())
            sample["names"].update(aliases)
            sample["aliases"].update((name,alias) for alias in aliases)


sys.setprofile(profile)
import pytest


class Capture:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self,item,nextitem):
        global ACTIVE
        ACTIVE = item.nodeid
        observations[ACTIVE] = {"functions":set(), "names":set(), "aliases":set()}
        try:
            yield
        finally:
            ACTIVE = None

    def pytest_runtest_logreport(self,report):
        outcomes.setdefault(report.nodeid,{})[report.when] = report.outcome


status = pytest.main(sys.argv[1:], plugins=[Capture()])
sys.setprofile(None)
mod = sys.modules[MODULE]
assert Path(mod.__file__).resolve() == TARGET
record = {"module":MODULE, "exports":sorted(exports(mod)), "outcomes":outcomes,
          "tests":{n:{k:sorted(v) for k,v in data.items()} for n,data in observations.items()},
          "import_calls":{str(n):sorted(v) for n,v in call_lines.items()}}
Path(os.environ["AUTO_OBSERVATIONS"]).write_text(json.dumps(record,sort_keys=True),encoding="utf8")
sys.exit(int(status))

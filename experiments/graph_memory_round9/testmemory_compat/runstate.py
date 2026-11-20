"""Run a frozen set of tests in one checkout, recording each observed coverage context."""
import collections
import gzip
import json
import os
import sys
import time
from pathlib import Path
import coverage
import pytest


def main():
    root = Path.cwd().resolve()
    prefix = root/"sympy"
    path, dest = map(Path,sys.argv[1:3])
    nodes = json.loads(path.read_bytes())
    sys.path.insert(0,str(root))
    cov = coverage.Coverage(data_file=None,config_file=False,include=[str(prefix/"*")])
    reports=collections.defaultdict(list)
    class Switch:
        @pytest.hookimpl(hookwrapper=True,tryfirst=True)
        def pytest_runtest_protocol(self,item,nextitem):
            cov.switch_context(item.nodeid)
            try:
                yield
            finally:
                cov.switch_context("shared")
        def pytest_runtest_logreport(self,report):
            reports[report.nodeid].append([report.when,report.outcome,report.duration])
    cov.start()
    cov.switch_context("shared")
    start=time.monotonic()
    code=pytest.main(["-q","--disable-warnings","-o","addopts=","--tb=line",*nodes],plugins=[Switch()])
    wall=time.monotonic()-start
    cov.stop()
    module=sys.modules.get("sympy")
    assert module and Path(module.__file__).resolve().is_relative_to(root)
    data=cov.get_data()
    contexts=collections.defaultdict(dict)
    for name in sorted(data.measured_files()):
        file=Path(name).resolve()
        if not file.is_relative_to(prefix) or "tests" in file.relative_to(prefix).parts or file.suffix!=".py":
            continue
        rel=file.relative_to(root).as_posix()
        lines=collections.defaultdict(list)
        for num,names in data.contexts_by_lineno(name).items():
            for ctx in names:
                lines[ctx or "shared"].append(num)
        for ctx,ids in lines.items():
            contexts[ctx][rel]=sorted(ids)
    payload=dict(code=int(code),wall=wall,reports=reports,contexts=contexts,
                 python=sys.version.split()[0],coverage=coverage.__version__,pytest=pytest.__version__)
    dest.write_bytes(gzip.compress(json.dumps(payload,separators=(",",":")).encode(),mtime=0))
if __name__=="__main__":
    main()

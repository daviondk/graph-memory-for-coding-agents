"""A fixed pytest invocation in an audited copy of the QuixBugs Python suite."""
import json
from pathlib import Path
import sys

import pytest


class Evidence:
    def __init__(self):
        self.collected = []
        self.reports = []

    def pytest_collection_modifyitems(self, items):
        self.collected = [item.nodeid for item in items]

    def pytest_runtest_logreport(self, report):
        self.reports.append([report.nodeid, report.when, report.outcome])


if __name__ == "__main__":
    destination, state, node = sys.argv[1:]
    sys.path.insert(0, str(Path.cwd()))
    audit = Evidence()
    args = ["-vv", "--no-header", "--color=no", "--tb=short", "-p", "no:cacheprovider", node]
    if state == "correct":
        args.insert(0, "--correct")
    result = int(pytest.main(args, plugins=[audit]))
    Path(destination).write_text(json.dumps(dict(collected=audit.collected, reports=audit.reports,
                                                rc=result, pytest=pytest.__version__)), encoding="utf8")
    raise SystemExit(result)

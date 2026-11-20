"""Finish the roster as solver manifests become available; one independent grader at a time."""
import time
from grade import ARMS, HERE, ROOT, TARGETS, grade, read, summarize
from seal import main as seal

roster=read(ROOT/'assignments.json')
assert len(roster)==12 and {tuple(v) for v in roster}=={(i,a) for i in TARGETS for a in ARMS}
while True:
    for iid,arm in roster:
        if not (HERE/'receipts'/iid/(arm+'.json')).exists() and (ROOT/'runs'/iid/arm/'complete.json').is_file():
            if grade(iid,arm):summarize()
    if all((HERE/'receipts'/iid/(a+'.json')).is_file() for iid,a in roster):
        seal()
        break
    time.sleep(8)


"""Observe native line/call events for the specified production file during a single prior pytest run."""
import json
import os
from pathlib import Path
import sys
import time

repo=Path(sys.argv[1]);file=sys.argv[2];target=sys.argv[3];out=Path(sys.argv[4])
wanted=os.path.normcase(str((repo/target).resolve()))
stats={'lines':set(),'calls':set()}
def trace(frame,event,arg):
    if event=='call':
        if os.path.normcase(frame.f_code.co_filename)!=wanted:return None
        stats['calls'].add(frame.f_code.co_qualname.replace('.<locals>.','.'))
    elif event=='line':stats['lines'].add(frame.f_lineno)
    return trace
sys.path.insert(0,str(repo));os.chdir(repo)
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.settrace(trace)
import pytest
outcomes=[]
class Plugin:
    def pytest_runtest_logreport(self,report):
        outcomes.append((report.nodeid,report.when,report.outcome))
started=time.perf_counter()
code=pytest.main(['-q','-o','addopts=',file],plugins=[Plugin()])
sys.settrace(None)
true_module=Path(sys.modules['loguru'].__file__).resolve()
assert true_module.is_relative_to(repo.resolve())
out.write_text(json.dumps({'status':int(code),'module':str(true_module),'seconds':time.perf_counter()-started,
                         'calls':sorted(stats['calls']),'lines':sorted(stats['lines']),'tests':outcomes}),encoding='utf8')

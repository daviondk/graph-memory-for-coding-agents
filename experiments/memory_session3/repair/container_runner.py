"""Container-side runner. A new isolated child receives only one input and program, never the oracle."""
import ast
import json
import subprocess
import sys
import time
import pytest

CHILD = """
import contextlib, io, json, os, resource, sys
request=json.load(sys.stdin)
resource.setrlimit(resource.RLIMIT_AS, (160*1024**2,160*1024**2))
namespace={'__name__':'candidate'}
try:
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(request['code'],'candidate.py','exec'),namespace)
        value=namespace[request['name']](*request['input'])
        if request['as_list']:value=list(value)
    print(json.dumps({'kind':'return','repr':repr(value)}))
except BaseException as e:
    print(json.dumps({'kind':'error','error':type(e).__name__,'detail':str(e)[:180]}))
"""

def main():
    job=json.load(sys.stdin);rows=[]
    for case in job['cases']:
        expected=case['expected']
        if job['name']=='hanoi':expected=[tuple(x) for x in expected]
        if job['name']=='sqrt':expected=pytest.approx(expected,abs=case['input'][-1])
        payload={'name':job['name'],'code':job['code'],'input':case['input'],'as_list':job['name'] in ('flatten','kheapsort')}
        start=time.monotonic()
        try:
            r=subprocess.run([sys.executable,'-I','-c',CHILD],input=json.dumps(payload),text=True,capture_output=True,timeout=1.8)
            obs=json.loads(r.stdout) if r.returncode==0 else {'kind':'process_error','returncode':r.returncode}
            good=obs['kind']=='return' and ast.literal_eval(obs['repr'])==expected
        except subprocess.TimeoutExpired:
            obs={'kind':'timeout'};good=False
        except (ValueError,SyntaxError) as err:
            obs={'kind':'unreadable','error':str(err)[:180]};good=False
        rows.append({'key':case['key'],'ok':good,'observation':obs,'seconds':time.monotonic()-start})
    print(json.dumps(rows))
if __name__=='__main__':main()


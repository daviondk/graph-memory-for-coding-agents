"""Execute only Python/unittest in a closed, mount-free, read-only container."""
from concurrent.futures import ThreadPoolExecutor
import json,subprocess
from study import IMAGE

WORKER=r"""
import contextlib,io,json,sys,unittest,traceback
j=json.load(sys.stdin)
ns={"__name__":"fixture"}
out=io.StringIO()
try:
 with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
  exec(compile(j["src"],"<masked-class>","exec"),ns)
  exec(compile(j["test"],"<authors-tests>","exec"),ns)
  suite=unittest.defaultTestLoader.loadTestsFromTestCase(ns[j["suite"]])
  res=unittest.TestResult();suite.run(res)
 f=len(res.failures);e=len(res.errors);s=len(res.skipped)
 result=dict(run=res.testsRun,failures=f,errors=e,skipped=s,passed=res.testsRun>0 and f+e+s==0,
  test_failures=[str(t) for t,_ in res.failures],test_errors=[str(t) for t,_ in res.errors])
except Exception as exc:
 result=dict(run=0,passed=False,setup_error=type(exc).__name__+": "+str(exc)[:240])
print(json.dumps(result))
"""
WRAPPER=r"""
import json,subprocess,sys
args=json.load(sys.stdin);out={}
for j in args["jobs"]:
 try:
  p=subprocess.run([sys.executable,"-I","-B","-c",args["worker"]],input=json.dumps(j),text=True,capture_output=True,timeout=args["timeout"])
  rec=json.loads(p.stdout) if p.returncode==0 else dict(run=0,passed=False,process_exit=p.returncode)
 except subprocess.TimeoutExpired:rec=dict(run=0,passed=False,timeout=True)
 out[j["id"]]=rec
print(json.dumps(out))
"""
def execute(jobs,timeout):
    if not jobs:return {}
    cmd=["docker","run","--rm","-i","--network","none","--read-only","--user","65534:65534","--cap-drop","ALL",
         "--security-opt","no-new-privileges","--pids-limit","48","--memory","192m","--cpus","1",
         "--entrypoint","python",IMAGE,"-I","-B","-c",WRAPPER]
    def one(batch):
        v=subprocess.run(cmd,input=json.dumps(dict(jobs=batch,worker=WORKER,timeout=timeout)),text=True,
              encoding="utf-8",capture_output=True,timeout=90+timeout*len(batch))
        if v.returncode:raise RuntimeError(v.stderr[-1200:])
        res=json.loads(v.stdout)
        assert set(res)=={j["id"] for j in batch}
        return res
    chunks=[jobs[i::3] for i in range(min(3,len(jobs)))]
    out={}
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        for part in pool.map(one,chunks):
            assert not set(part)&set(out);out.update(part)
    return out

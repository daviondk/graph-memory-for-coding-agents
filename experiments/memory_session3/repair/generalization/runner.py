"""Container entrypoint. One fresh constrained interpreter for a single code/input pair."""
import json,subprocess,sys,time

CHILD = """
import contextlib,io,itertools,json,os,resource,sys
req=json.load(sys.stdin)
resource.setrlimit(resource.RLIMIT_AS,(144*1024**2,144*1024**2))
try:
    namespace={'__name__':'candidate'}
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(req['code'],'candidate.py','exec'),namespace)
        v=namespace[req['name']](*req['input'])
        if req['name'] in ('flatten','kheapsort'):v=list(itertools.islice(v,1000))
    result=json.dumps({'status':'return','value':v},allow_nan=False)
    print(result if len(result)<800000 else json.dumps({'status':'oversized_output'}))
except BaseException as e:
    print(json.dumps({'status':'error','type':type(e).__name__,'message':str(e)[:160]}))
"""
job=json.load(sys.stdin);output=[]
for case in job['cases']:
    start=time.monotonic()
    try:
        run=subprocess.run([sys.executable,'-I','-c',CHILD],
            input=json.dumps({'name':job['name'],'input':case['input'],'code':job['code']}),
            text=True,capture_output=True,timeout=.9)
        actual=json.loads(run.stdout) if run.returncode==0 else {'status':'child_exit','returncode':run.returncode}
    except subprocess.TimeoutExpired:actual={'status':'timeout'}
    except (ValueError,TypeError):actual={'status':'unreadable'}
    output.append({'key':case['key'],'observation':actual,'seconds':time.monotonic()-start})
print(json.dumps(output,allow_nan=False))

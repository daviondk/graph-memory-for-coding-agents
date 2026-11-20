"""Evaluate the restricted pure functions; no benchmark code is called by the parent process."""
import ast, builtins, contextlib, copy, io, json, math, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from safe_ast import checked, BUILTINS, restricted_import

class Steps(Exception):pass
def bounded(f):
    left=15000
    def trace(frame,event,arg):
        nonlocal left
        if event=="line":
            left-=1
            if left<0:raise Steps()
        return trace
    try:
        sys.settrace(trace)
        return f()
    finally:sys.settrace(None)
def floats(x):
    return isinstance(x,float) or isinstance(x,(list,tuple)) and all(isinstance(i,float) for i in x)
def close(x,y,tol):
    import sysconfig, os, site
    os.environ["OPENBLAS_NUM_THREADS"]="1"
    path=sysconfig.get_paths()["purelib"]
    if path not in sys.path:sys.path.append(path)
    sys.path.append(site.getusersitepackages())
    import numpy as np
    return bool(np.allclose(x,y,rtol=1.e-7,atol=tol))
def outcome(data):
    try:
        tree=checked(data["source"])
        env={n:getattr(builtins,n) for n in BUILTINS}
        env["__import__"]=restricted_import
        scope={"__builtins__":env}
        bounded(lambda:exec(compile(tree,"observed_function","exec"),scope))
        entry=scope[data["name"]]
    except BaseException as e:return {"status":"invalid","reason":type(e).__name__+":"+str(e)[:70]}
    bits=[];errors=[]
    for check in data["examples"]:
        try:
            if isinstance(check,str):
                expr=ast.parse(check).body[0].test
                ok=bounded(lambda:bool(eval(compile(ast.Expression(expr),"observed_assert","eval"),scope)))
            else:
                args,y,tol=check
                result=bounded(lambda:entry(*copy.deepcopy(args)))
                ok=result==y
                if not ok and (tol or floats(y)):ok=close(result,y,tol or 1e-6)
            bits.append(int(bool(ok)));errors.append("")
        except BaseException as e:bits.append(0);errors.append(type(e).__name__)
    return {"status":"ok","bits":bits,"errors":errors}
if __name__=="__main__":
    try:
        data=json.load(sys.stdin)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):o=outcome(data)
    except BaseException as e:o={"status":"infrastructure","reason":type(e).__name__}
    print(json.dumps(o))


"""Execute trusted publisher tests and a constrained candidate in distinct namespaces."""
import builtins,contextlib,io,json,os,site,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from safe_ast import checked,BUILTINS,restricted_import
def run(obj):
    safe={k:getattr(builtins,k) for k in BUILTINS};safe["__import__"]=restricted_import
    scope={"__builtins__":safe}
    try:exec(compile(checked(obj["source"]),"candidate","exec"),scope)
    except BaseException as e:return {"status":"invalid","why":type(e).__name__}
    name=obj["name"];env={name:scope[name],"__name__":"author_tests"}
    os.environ["OPENBLAS_NUM_THREADS"]="1"
    sys.path.append(site.getusersitepackages())
    try:
        import numpy
    except ImportError:return {"status":"infrastructure","why":"missing numpy"}
    try:
        exec(compile(obj["suite"],"publisher_suite","exec"),env)
        if obj["extra_call"]:env["check"](scope[name])
        return {"status":"pass"}
    except BaseException as e:return {"status":"fail","why":type(e).__name__}
if __name__=="__main__":
    try:
        data=json.load(sys.stdin)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):result=run(data)
    except BaseException as e:result={"status":"infrastructure","why":type(e).__name__}
    print(json.dumps(result))


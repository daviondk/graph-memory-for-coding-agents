"""Answer only with fingerprints of outputs on supplied inputs. This worker never receives expected outputs."""
import ast,builtins,contextlib,copy,hashlib,io,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runner import bounded
from safe_ast import checked,BUILTINS,restricted_import
def freeze(x):
    if type(x) in (dict,):
        return ("dict",sorted((repr(freeze(k)),freeze(v)) for k,v in x.items()))
    if isinstance(x,(list,tuple)):
        return (type(x).__name__,[freeze(v) for v in x])
    if isinstance(x,(set,frozenset)):
        return ("set",sorted(repr(freeze(v)) for v in x))
    if type(x) in (int,bool,str,float,type(None)):return (type(x).__name__,x)
    return ("unsupported",type(x).__name__)
def main(data):
    safe={n:getattr(builtins,n) for n in BUILTINS}
    safe["__import__"]=restricted_import;scope={"__builtins__":safe}
    try:
        tree=checked(data["source"]);bounded(lambda:exec(compile(tree,"candidate","exec"),scope));f=scope[data["name"]]
    except BaseException as e:return ["invalid:"+type(e).__name__]*len(data["args"])
    out=[]
    for args in data["args"]:
        try:
            v=bounded(lambda:f(*copy.deepcopy(args)))
            s=json.dumps(freeze(v),ensure_ascii=True,separators=(",",":"))
            out.append(hashlib.sha256(s.encode()).hexdigest())
        except BaseException as e:out.append("error:"+type(e).__name__)
    return out
if __name__=="__main__":
    try:
        obj=json.load(sys.stdin)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):ret=main(obj)
        print(json.dumps({"status":"ok","labels":ret}))
    except BaseException as e:print(json.dumps({"status":"process","reason":type(e).__name__}))


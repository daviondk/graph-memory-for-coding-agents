"""Execute only pre-screened pure programs in the existing research sandbox and return bounded values."""
import ast,builtins,contextlib,io,json,math,pathlib,sys
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/"memory_session6/repair"))
from worker import permitted,PERMIT,restricted_import

def display(x,depth=0):
    if depth>4:raise ValueError()
    if x is None or type(x) in (bool,int,str):
        if len(repr(x))>100:raise ValueError()
        return repr(x)
    if type(x) is float and math.isfinite(x):return repr(round(x,8))
    if type(x) in (list,tuple,dict,set,frozenset) and len(x)<=12:
        if type(x) is dict:
            body=", ".join(sorted(display(a,depth+1)+": "+display(b,depth+1) for a,b in x.items()))
            return "{"+body+"}"
        vals=[display(a,depth+1) for a in x]
        if isinstance(x,(set,frozenset)):
            return ("set" if isinstance(x,set) else "frozenset")+"(["+", ".join(sorted(vals))+"])"
        if type(x) is tuple:return "("+", ".join(vals)+("," if len(vals)==1 else "")+")"
        return "["+", ".join(vals)+"]"
    raise ValueError()

def evaluate(d):
    text=pathlib.Path(d["file"]).read_text(encoding="utf8")
    env={k:getattr(builtins,k) for k in PERMIT}
    env.update(__import__=restricted_import,print=lambda *a,**kw:None)
    compiled=compile(permitted(text),"candidate.py","exec")
    def entry():
        scope={"__builtins__":env.copy()}
        exec(compiled,scope)
        return scope[d["entry"]]
    tests={d["entry"]:entry()}
    try:
        for imp in d["imports"]:exec(imp,tests)
        exec(d["public_assert"],tests)
        public=True
    except BaseException:public=False
    outputs=[]
    for literal in d["probes"]:
        try:
            value=entry()(*ast.literal_eval(literal))
            shown=display(value)
            outputs.append(shown if len(shown)<=120 else None)
        except BaseException:outputs.append(None)
    return {"state":"ok","public":public,"vec":outputs}
if __name__=="__main__":
    d=json.load(sys.stdin)
    try:result=evaluate(d)
    except BaseException as e:result={"state":"invalid:"+type(e).__name__,"public":False,"vec":[None]*len(d["probes"])}
    print(json.dumps(result,ensure_ascii=True))


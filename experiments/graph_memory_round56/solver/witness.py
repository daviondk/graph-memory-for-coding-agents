"""Retrieve runnable contract evidence with no access to the target doctests."""
from collections import Counter
import re
import sys
from study import *
from grade import parse_answer
import isolation as sandbox

PRIORITY=("full_bm25","file8","file_all","global32","contract")
BUILTINS=set("abs all any bool bytes chr dict enumerate filter float frozenset int iter len list map max min next ord range repr reversed round set slice sorted str sum tuple zip".split())
PURE_ATTRIBUTES=set("get items keys values lower upper strip split join count index".split())
MODULES=set("more_itertools more mit mi recipes toolz itertoolz functoolz dicttoolz boltons iterutils strutils dictutils listutils setutils mathutils statsutils timeutils".split())

def clean_expression(node,symbol):
    # Limit external references to the named symbol and deterministic builtin calls.
    class Alias(ast.NodeTransformer):
        def visit_Attribute(self,n):
            if n.attr==symbol and isinstance(n.value,ast.Name) and n.value.id in MODULES:
                return ast.copy_location(ast.Name(id=symbol,ctx=ast.Load()),n)
            return self.generic_visit(n)
    import copy
    tree=Alias().visit(copy.deepcopy(node))
    defined={n.arg for n in ast.walk(tree) if isinstance(n,ast.arg)}
    defined.update(n.id for n in ast.walk(tree) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store))
    for n in ast.walk(tree):
        if isinstance(n,ast.Name) and n.id not in BUILTINS|defined|{symbol}:return None
        if isinstance(n,ast.Attribute) and n.attr not in PURE_ATTRIBUTES:return None
        if isinstance(n,(ast.NamedExpr,ast.Await,ast.Yield,ast.YieldFrom)):return None
    return ast.unparse(tree)

def assertions(text,symbol):
    # An observation may be cropped at its last line. Retain the largest complete prefix.
    lines=text.splitlines()
    while lines:
        try:tree=ast.parse("\n".join(lines));break
        except (SyntaxError,IndentationError):lines.pop()
    if not lines:return []
    found=[]
    for stmt in ast.walk(tree):
        left=right=None;op="eq"
        if isinstance(stmt,ast.Assert):
            t=stmt.test
            if isinstance(t,ast.Compare) and len(t.ops)==1 and isinstance(t.ops[0],ast.Eq):
                left,right=t.left,t.comparators[0]
            elif not isinstance(t,ast.Compare):
                neg=isinstance(t,ast.UnaryOp) and isinstance(t.op,ast.Not)
                left=t.operand if neg else t;right=ast.Constant(not neg);op="bool"
        elif isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Call):
            c=stmt.value
            if isinstance(c.func,ast.Attribute) and c.func.attr=="assertEqual" and len(c.args)==2:left,right=c.args
            elif isinstance(c.func,ast.Attribute) and c.func.attr in ("assertTrue","assertFalse") and len(c.args)==1:
                left,right,op=c.args[0],ast.Constant(c.func.attr=="assertTrue"),"bool"
        if left is None:continue
        a,b=clean_expression(left,symbol),clean_expression(right,symbol)
        if a is None or b is None:continue
        calls=lambda s:any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==symbol for n in ast.walk(ast.parse(s,mode="eval")))
        if calls(b) and not calls(a) and op=="eq":a,b=b,a
        if calls(a) and not calls(b):found.append((a,op,b))
    return found

def probes():
    tasks=read("selections.json.gz");history=read("history.json.gz");out={}
    for q,r in tasks.items():
        t=r["task"];es=history[t["repo"]]["episodes"]
        order=sorted(range(len(es)),key=lambda j:(t["path"] not in es[j]["anchors"],-es[j]["i"],es[j]["path"],es[j]["address"]))
        picked={}
        for j in order:
            e=es[j]
            if not re.search(r"\b"+re.escape(t["name"])+r"\s*\(",e["text"]):continue
            for obs in assertions(e["text"],t["name"]):
                if obs in picked:continue
                picked[obs]=[j,e["sha"]]
                if len(picked)==12:break
            if len(picked)==12:break
        out[q]=[dict(expr=k[0],op=k[1],expected=k[2],episode_id=v[0],sha=v[1]) for k,v in picked.items()]
    return out

WORKER=r'''
import ast,contextlib,hashlib,importlib,io,json,sys,zipfile
j=json.load(sys.stdin)
sys.path.insert(0,"/tmp/pkg.zip")
def canon(v):
    if v is None or isinstance(v,(bool,int,str)):return [type(v).__name__,v]
    if isinstance(v,float):return ["float",repr(v)]
    if isinstance(v,bytes):return ["bytes",v.hex()]
    if isinstance(v,(list,tuple)):return [type(v).__name__,[canon(x) for x in v]]
    if isinstance(v,(set,frozenset)):return [type(v).__name__,sorted([canon(x) for x in v],key=repr)]
    if isinstance(v,dict):return ["dict",sorted([[canon(k),canon(x)] for k,x in v.items()],key=repr)]
    raise ValueError("noncanonical")
values=[]
with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
    try:
        module=importlib.import_module(j["path"][:-3].replace("/","."))
        old=getattr(module,j["name"])
        with zipfile.ZipFile("/tmp/pkg.zip") as z:root=ast.parse(z.read(j["path"]))
        node=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name==j["name"])
        node.body=ast.parse(j["answer"]).body[0].body
        tree=ast.Module(body=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),node],type_ignores=[])
        exec(compile(ast.fix_missing_locations(tree),"<candidate>","exec"),module.__dict__)
        new=getattr(module,j["name"])
        for mod in list(sys.modules.values()):
            if not getattr(mod,"__name__","").startswith(j["path"].split("/")[0]):continue
            for n,v in list(vars(mod).items()):
                if v is old:setattr(mod,n,new)
        for e in j["checks"]:
            try:
                env={j["name"]:new}
                actual=eval(e["expr"],env);expected=eval(e["expected"],env)
                if e["op"]=="bool":actual=bool(actual)
                ok=bool(actual==expected)
                try:tag=hashlib.sha256(json.dumps(canon(actual),sort_keys=True,allow_nan=False).encode()).hexdigest()
                except BaseException:tag=None
                values.append([tag,ok])
            except BaseException as exc:values.append([None,False])
    except BaseException:values=[]
print(json.dumps({"values":values}))
'''

def decide():
    obs=probes();write("witness-observations.json.gz",obs)
    predictions=read("answers.json.gz");refs=read("assignments.json.gz");selected=read("selections.json.gz")
    candidates={};jobs=[]
    for q,arms in refs.items():
        task=selected[q]["task"];by_code={}
        for arm in PRIORITY:
            h=arms[arm]["hash"]
            code,why=parse_answer(predictions[h]["text"],task["name"])
            identity=digest((code if code else predictions[h]["text"]).encode())
            if identity in by_code:continue
            by_code[identity]=[arm,h]
            if code and obs[q]:
                jobs.append(dict(id=q+"|"+h,repo=task["repo"],path=task["path"],name=task["name"],answer=code,checks=obs[q]))
        candidates[q]=list(by_code.values())
    sandbox.WORKER=WORKER
    outcomes=sandbox.execute(jobs)
    decisions={}
    for q,rows in candidates.items():
        n=len(obs[q])
        matrix={}
        for arm,h in rows:
            vals=outcomes.get(q+"|"+h,{}).get("values",[])
            matrix[arm]=vals if len(vals)==n else [[None,False] for _ in range(n)]
        def accuracy(arm):return sum(x[1] for x in matrix[arm])
        def agreement(arm):
            return sum(t is not None and t==matrix[other][i][0] for i,(t,_) in enumerate(matrix[arm])
                       for other in matrix if other!=arm)
        decisions[q]=dict(implementations=rows,observations=n,old_expected=max(matrix,key=accuracy),
                          consensus=max(matrix,key=agreement),
                          old_scores={a:accuracy(a) for a in matrix},consensus_scores={a:agreement(a) for a in matrix})
    write("witness-probes.json.gz",outcomes);write("witness-decisions.json.gz",decisions)
    names=("WITNESS_PROTOCOL_RU.md","witness.py","witness-observations.json.gz","witness-probes.json.gz","witness-decisions.json.gz")
    write("witness-seal.json",{n:digest((HERE/n).read_bytes()) for n in names})
    print("probes",sum(map(len,obs.values())),"in",sum(bool(x) for x in obs.values()),"questions, actual jobs",len(jobs),
          "distinct policies",sum(r["old_expected"]!=r["consensus"] for r in decisions.values()))
if __name__=="__main__":decide()

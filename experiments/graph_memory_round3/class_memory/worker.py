"""Run a selected publisher method-test suite under a restricted execution environment in a time/memory bounded child."""
import ast,builtins,collections,contextlib,datetime,decimal,functools,heapq,io,itertools,json,math,operator,random,re,statistics,string,sys,textwrap,typing,unittest
MODULES={x.__name__:x for x in (math,re,collections,datetime,decimal,itertools,typing,statistics,string,random,functools,heapq,operator)}
DENY=set("eval exec compile open input globals locals vars getattr setattr delattr __import__ breakpoint help dir quit exit super system popen spawn read_text write_text read_bytes write_bytes load_module import_module get_data get_code get_source fromfile tofile exit_class enter_context".split())
BADATTR=set("sys os modules _os _sys environ builtins loader importlib stdout stdin stderr cmdclass".split())
def check(node,mode):
    for n in ast.walk(node):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            mods=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module]
            if any(m not in MODULES for m in mods):raise ValueError("import outside pure allowlist")
            if any(a.name in DENY or a.name in BADATTR or a.name.startswith("_") for a in n.names):raise ValueError("import symbol")
        if isinstance(n,ast.Name) and (n.id in DENY or n.id.startswith("__")):raise ValueError("forbidden name")
        if isinstance(n,ast.Attribute):
            if n.attr in BADATTR or n.attr in DENY or n.attr.startswith("__"):raise ValueError("forbidden attribute")
        if mode=="candidate" and isinstance(n,(ast.ClassDef,ast.Global,ast.Nonlocal,ast.AsyncFunctionDef,ast.Delete)) and not isinstance(n,ast.Delete):raise ValueError("forbidden declaration")
def parse_candidate(src,name):
    txt=src.strip()
    match=re.findall(r"```(?:python|py)?\s*\n(.*?)```",txt,re.S|re.I)
    if match:txt=match[0]
    tree=ast.parse(textwrap.dedent(txt))
    if len(tree.body)==1 and isinstance(tree.body[0],ast.ClassDef):
        tree=tree.body[0]
    f=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    if len(f)!=1:raise ValueError("expected one named method")
    f=f[0];f.decorator_list=[];check(f,"candidate");return f
def safe_import(name,globals=None,locals=None,fromlist=(),level=0):
    if level or name not in MODULES or any(a.startswith("_") or a in DENY or a in BADATTR for a in fromlist or ()):raise ImportError(name)
    return MODULES[name]
def run(r):
    name=r["name"];cls=r["class"];grade=r["grade"]
    tree=ast.parse(r["source"]);target=next(c for c in tree.body if isinstance(c,ast.ClassDef) and c.name==cls)
    orig=next(f for f in target.body if isinstance(f,ast.FunctionDef) and f.name==name)
    if grade=="stub":orig.body=[ast.Raise(ast.Call(ast.Name("NotImplementedError",ast.Load()),[],[]),None)]
    if grade=="generated":
        try:f=parse_candidate(r["candidate"],name)
        except Exception as exc:return dict(status="invalid",why=str(exc)[:140])
        f.decorator_list=orig.decorator_list;target.body[target.body.index(orig)]=f
    check(tree,"published");ast.fix_missing_locations(tree)
    allow=set("abs all any ascii bin bool callable chr classmethod complex dict divmod enumerate filter float format frozenset hex int isinstance issubclass iter len list map max min next object oct ord pow print property range repr reversed round set slice sorted staticmethod str sum tuple type zip BaseException Exception ArithmeticError ValueError TypeError IndexError KeyError RuntimeError AttributeError ZeroDivisionError StopIteration NotImplementedError AssertionError".split())
    env={k:getattr(builtins,k) for k in allow};env.update(__build_class__=builtins.__build_class__,__import__=safe_import)
    ctx={"__name__":"target","__builtins__":env}
    for a in r["imports"]:
        im=ast.parse(a);check(im,"published");exec(compile(im,"imports","exec"),ctx)
    exec(compile(tree,"class","exec"),ctx)
    ts=dict(ctx);ts["unittest"]=unittest;ts["__name__"]="publisher_tests"
    testtree=ast.parse(r["tests"]);check(testtree,"publisher")
    exec(compile(testtree,"author_tests","exec"),ts)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ts[r["testclass"]])
    result=unittest.TestResult();random.seed(314159);suite.run(result)
    fails=[(case.id().rsplit(".",1)[-1],exc.splitlines()[-1][:120]) for case,exc in result.failures+result.errors]
    return dict(status="pass" if result.wasSuccessful() and result.testsRun else "fail",total=result.testsRun,passed=result.testsRun-len(fails)-len(result.skipped),failures=fails,skipped=len(result.skipped))
if __name__=="__main__":
    try:
        payload=json.load(sys.stdin)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):receipt=run(payload)
    except BaseException as exc:receipt=dict(status="harness",why=type(exc).__name__+":"+str(exc)[:140])
    print(json.dumps(receipt,ensure_ascii=True))

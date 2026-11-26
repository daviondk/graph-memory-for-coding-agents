"""Run public doctests inside an offline, read-only, unprivileged Python container."""
import base64
from concurrent.futures import ThreadPoolExecutor
from study import *

WORKER = r'''
import ast, contextlib, copy, doctest, importlib, io, json, sys, traceback, zipfile
j=json.load(sys.stdin)
sys.path.insert(0,"/tmp/pkg.zip")
with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
    try:
        module=importlib.import_module(j["path"][:-3].replace("/","."))
        original=getattr(module,j["name"])
        doc=original.__doc__
        if j["kind"]!="reference":
            with zipfile.ZipFile("/tmp/pkg.zip") as z:
                root=ast.parse(z.read(j["path"]))
            original_node=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name==j["name"])
            replacement=ast.parse("def stub():\n    raise NotImplementedError").body[0] if j["kind"]=="stub" else ast.parse(j["answer"]).body[0]
            original_node.body=copy.deepcopy(replacement.body)
            standalone=ast.Module(body=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),original_node],type_ignores=[])
            exec(compile(ast.fix_missing_locations(standalone),"<candidate>","exec"),module.__dict__)
            new=getattr(module,j["name"])
            for obj in list(sys.modules.values()):
                if not getattr(obj,"__name__","").startswith(j["path"].split("/")[0]):continue
                for name,value in list(vars(obj).items()):
                    if value is original:setattr(obj,name,new)
        t=doctest.DocTestParser().get_doctest(doc,dict(vars(module)),j["name"],j["path"],0)
        output=io.StringIO()
        runner=doctest.DocTestRunner()
        checked=runner.run(t,out=output.write)
        result=dict(run=checked.attempted,failed=checked.failed,passed=(checked.attempted>0 and not checked.failed),
                    failure_digest=__import__("hashlib").sha256(output.getvalue().encode()).hexdigest())
    except BaseException as e:
        result={"run":0,"passed":False,"error":type(e).__name__+": "+str(e)[:180]}
print(json.dumps(result))
'''
WRAPPER=r'''
import base64,json,subprocess,sys
j=json.load(sys.stdin)
with open("/tmp/pkg.zip","wb") as f:f.write(base64.b64decode(j["zip"]))
results={}
for job in j["jobs"]:
    try:
        p=subprocess.run([sys.executable,"-I","-B","-c",j["script"]],input=json.dumps(job),
                         text=True,capture_output=True,timeout=5)
        v=json.loads(p.stdout) if p.returncode==0 else {"run":0,"passed":False,"process_exit":p.returncode}
    except subprocess.TimeoutExpired:v={"run":0,"passed":False,"timeout":True}
    results[job["id"]]=v
print(json.dumps(results))
'''
def execute(tasks):
    parts=[]
    for repo in sorted(SPECS):
        group=[r for r in tasks if r["repo"]==repo]
        if not group:continue
        for i in range(0,len(group),16):parts.append((repo,group[i:i+16]))
    def run(part):
        repo,jobs=part
        pkg=(RAW/(repo.replace("/","__")+".zip")).read_bytes()
        assert digest(pkg)==read("pins.json")[repo]["package_sha"]
        cmd=["docker","run","--rm","-i","--network","none","--read-only","--user","65534:65534","--cap-drop","ALL",
             "--security-opt","no-new-privileges","--tmpfs","/tmp:rw,noexec,nosuid,size=32m,mode=1777",
             "--pids-limit","48","--memory","160m","--cpus","1","--entrypoint","python",IMAGE,"-I","-B","-c",WRAPPER]
        obj=dict(zip=base64.b64encode(pkg).decode(),jobs=jobs,script=WORKER)
        p=subprocess.run(cmd,input=json.dumps(obj),encoding="utf8",capture_output=True,timeout=90+len(jobs)*6)
        if p.returncode:raise RuntimeError(p.stderr[-1000:])
        out=json.loads(p.stdout);assert set(out)=={j["id"] for j in jobs}
        return out
    results={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for chunk in pool.map(run,parts):results.update(chunk)
    return results

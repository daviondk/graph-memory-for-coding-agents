"""Observe actual standard lookup operations in a new interpreter."""
import builtins,datetime,hashlib,importlib.machinery,json,os,sys,time
from pathlib import Path
from workloads import run,passed
root=Path.cwd().resolve()
sys.path.insert(0,str(root/"vendor"))
project,case,out=sys.argv[1:]
base=os.path.normcase(str(root)).rstrip("\\/")+os.sep
def rel(p):
    if not isinstance(p,(str,bytes,os.PathLike)):return None
    if isinstance(p,bytes):p=os.fsdecode(p)
    s=os.path.normcase(os.path.abspath(p))
    if not s.startswith(base):return None
    return s[len(base):].replace("\\","/")
def watched(p):return bool(p and (p.startswith("zones/") or p.startswith("vendor/")) and "__pycache__" not in p and ".dist-info/" not in p)
pos=set();neg=set();dirs=set();events=[];start=time.perf_counter()
def capture(bucket,k,kind):
    if k not in bucket:events.append([kind,k]);bucket.add(k)
original=importlib.machinery.PathFinder.find_spec
def record_spec(cls,fullname,path=None,target=None):
    s=original(fullname,path,target)
    if s:
        p=rel(s.origin) if s.origin and s.origin not in ("built-in","frozen") else None
        if watched(p):capture(pos,p,"resolved_import")
    return s
importlib.machinery.PathFinder.find_spec=classmethod(record_spec)
class Miss:
    def find_spec(self,fullname,path=None,target=None):
        paths=[rel(x) for x in (sys.path if path is None else path) if x]
        roots=[p for p in paths if p=="vendor" or (p and p.startswith("vendor/"))]
        if roots:
            capture(neg,"import:"+fullname,"unresolved_import")
            dirs.update(roots)
        return None
sys.meta_path.append(Miss())
real_isfile=os.path.isfile
def record_isfile(path):
    yes=real_isfile(path);p=rel(path)
    if watched(p):
        if yes:capture(pos,p,"file_exists")
        else:capture(neg,"path:"+p,"missing_file");dirs.add(p.rpartition("/")[0])
    return yes
os.path.isfile=record_isfile
def audit(kind,args):
    if kind!="open":return
    p=rel(args[0])
    if watched(p) and real_isfile(args[0]):capture(pos,p,"opened_file")
sys.addaudithook(audit)
value=run(project,case,root);ok=passed(project,case,value);seconds=time.perf_counter()-start
Path(out).write_text(json.dumps(dict(case=case,project=project,value=value,pass_test=ok,positive=sorted(pos),negative=sorted(neg),directories=sorted(dirs),events=events,elapsed=seconds),ensure_ascii=False,sort_keys=True),encoding="utf8")

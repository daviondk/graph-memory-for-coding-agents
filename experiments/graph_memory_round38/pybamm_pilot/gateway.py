"""Audited interface for one isolated public coding target. Checkout and role are supplied by the runner."""
import argparse,hashlib,json,msvcrt,os,subprocess,sys,time
from contextlib import contextmanager
from pathlib import Path
D=Path(__file__).resolve().parent
BASE=Path("D:/CodexResearch/x20-r38-pybamm-paired")
ACTORS=("scout","amber","cobalt","jade")
LIMIT={"scout":8,"amber":18,"cobalt":18,"jade":18}
def digest(data):return hashlib.sha256(data).hexdigest()
def legal(repo,name,write=False):
    p=(repo/name).resolve()
    if not p.is_relative_to(repo) or not p.is_file() or ".git" in p.parts:raise ValueError("unknown checkout file")
    if write and (p.suffix!=".py" or p.relative_to(repo).parts[0]!="pybamm" or "tests" in p.parts):
        raise ValueError("changes are limited to Python package source")
    return p
@contextmanager
def actor_lock(root):
    # Concurrent calls to one actor serialize the check, tool action, and audit append.
    with (root/"gateway.lock").open("r+b") as lock:
        while True:
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                break
            except OSError:
                time.sleep(.05)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

def invoke(actor,cmd,args,input_bytes=b""):
    root=BASE/actor
    repo=(root/"repo").resolve()
    log=root/"tool-log.jsonl"
    events=[json.loads(x) for x in log.read_text(encoding="utf8").splitlines()] if log.exists() else []
    if len(events)>=LIMIT[actor]:raise ValueError("interaction limit reached")
    if actor=="scout" and cmd not in ("list","search","read"):raise ValueError("scout is read-only")
    visible=[];spans=[]
    def show(p,i,s):
        name=p.relative_to(repo).as_posix()
        # Bound per-line display; only complete displayed source lines may become evidence cards.
        text=s if len(s)<=450 else s[:447]+"..."
        visible.append(f"{name}:{i} | {text}")
        if s==text:spans.append([name,i])
    try:
        if cmd=="list":
            pre=args[0] if args else ""
            names=sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*") if p.is_file())
            visible.extend(n for n in names if n.startswith(pre))
        elif cmd=="search":
            needle=args[0].casefold()
            if not needle:raise ValueError("empty search")
            pre=args[1] if len(args)>1 else ""
            for p in sorted(repo.rglob("*")):
                if (not p.is_file() or p.suffix not in (".py",".rst",".md",".txt") or not p.relative_to(repo).as_posix().startswith(pre)):continue
                for i,line in enumerate(p.read_text(encoding="utf-8",errors="replace").splitlines(),1):
                    if needle in line.casefold():show(p,i,line)
                    if len(visible)>=32:break
                if len(visible)>=32:break
        elif cmd=="read":
            p=legal(repo,args[0]);start,stop=map(int,args[1:3])
            if not 1<=start<=stop<=start+63:raise ValueError("read 1 to 64 lines")
            for i,line in enumerate(p.read_text(encoding="utf-8",errors="replace").splitlines(),1):
                if start<=i<=stop:show(p,i,line)
        elif cmd=="edit":
            p=legal(repo,args[0],True);pair=json.loads(input_bytes);old,new=pair["old"],pair["new"]
            if not isinstance(old,str) or not isinstance(new,str) or not old or old==new:raise ValueError("specify distinct old and new text")
            original=p.read_bytes()
            source=original.decode().replace("\r\n","\n")
            if source.count(old)!=1:raise ValueError("old text must occur exactly once")
            out=source.replace(old,new)
            if b"\r\n" in original:out=out.replace("\n","\r\n")
            p.write_bytes(out.encode())
            visible.append("Applied one unique replacement.")
        elif cmd=="test":
            cfg=json.loads((BASE/"environment.json").read_bytes())
            py=cfg.get("test_python")
            if not py:raise ValueError("public-test runtime unavailable")
            env=dict(os.environ,PYTHONPATH=str(repo),PYTHONDONTWRITEBYTECODE="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
            argv=[py,"-B","-m","pytest","-q","-p","no:cacheprovider","--tb=short"]
            if args:
                for name in args:
                    file=name.split("::",1)[0];p=legal(repo,file)
                    if "tests" not in p.parts:raise ValueError("choose public test path from checkout")
                argv.extend(args)
            else:raise ValueError("supply a public test file path or node ID")
            res=subprocess.run(argv,cwd=repo,env=env,capture_output=True,timeout=90)
            lines=(res.stdout+res.stderr).decode("utf-8",errors="replace").splitlines()
            visible=lines[-26:]+["exit "+str(res.returncode)]
        else:raise ValueError("unknown action")
    except (ValueError,IndexError,KeyError,OSError,subprocess.TimeoutExpired) as e:
        visible=["ERROR "+str(e)]
    text="\n".join(visible) or "(no matches)"
    while len(text.encode())>10000 and len(visible)>1:
        visible.pop()
        if spans:spans.pop()
        text="\n".join(visible)
    event=dict(action=cmd,args=args,output=text,displayed=spans,input_bytes=len(input_bytes),
               input_sha256=digest(input_bytes),bytes=len(text.encode()),index=len(events)+1)
    with log.open("a",encoding="utf8") as f:f.write(json.dumps(event,ensure_ascii=False)+"\n")
    return text

if __name__=="__main__":
    actor,cmd,*args=sys.argv[1:]
    if actor not in ACTORS:raise SystemExit("unknown actor")
    data=sys.stdin.buffer.read() if cmd=="edit" else b""
    with actor_lock(BASE/actor):
        print(invoke(actor,cmd,args,data))


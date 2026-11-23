"""Seal memory decisions from archived, bounded shell observations before scoring subsequent test receipts."""
import ast
import collections
import gzip
import hashlib
import json
import posixpath
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
RECEIPTS = WORK / "graph_memory_round15/test_receipts"
UPSTREAM = Path("D:/CodexResearch/x20-official-vibe/VibeMemBench")
sys.path.insert(0, str(RECEIPTS))
from receipt_policy import terminal

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read(p):
    raw = p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix == ".gz" else raw)

def put(name, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    (ROOT / name).write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)

FILE = r"(?:\./)?(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py"
POS = r"(?:/?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)"
CD = re.compile(r"\A\s*cd\s+(" + POS + r")\s*&&\s*", re.S)
SELECT = re.compile(FILE + r"(?:::[\w.-]+(?:\[[A-Za-z0-9_.-]+\])?)*\Z")
CONFIG = {"conftest.py", "pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini", "setup.py", "__init__.py"}
def key(item):
    cmd = item["cmd"].strip()
    cd = CD.match(cmd)
    cwd = cd[1] if cd else "/testbed"
    repo_root = "/" + item["repo"].split("/")[-1]
    if cwd != "/testbed" and not (cwd.lower() == repo_root.lower() or cwd.lower().startswith(repo_root.lower() + "/")):
        return None
    short = cmd[cd.end():] if cd else cmd
    if not re.match(r"^(?:pytest|py\.test|python(?:3(?:\.\d+)?)?\s+-m\s+pytest)\s", short):
        return None
    if any(s in short for s in ("&&", ";", "||", "| tee", "$", "\n", "<", "\x60")):
        return None
    if ">" in re.sub(r"2>&1", "", short):
        return None
    args = item["kind"]["args"]
    start = 1 if args[0] in ("pytest", "py.test") else 3
    selector = None
    filtered = False
    parts = iter(args[start:])
    for a in parts:
        if a in {"-k", "-m"}:
            if not next(parts, ""): return None
            filtered = True
        elif a.startswith("--"):
            if not re.fullmatch(r"--(?:tb=(short|long|line|no|native|auto)|maxfail=\d+|disable-warnings|no-header|no-summary|color=(auto|yes|no))", a): return None
        elif re.fullmatch(r"-[qvsx]+", a): pass
        elif SELECT.fullmatch(a) and not selector and ".." not in a.split("/"): selector = a
        else: return None
    if not selector: return None
    return {"root":cwd, "path":posixpath.normpath(posixpath.join(cwd,selector.split("::")[0])), "selector":selector, "level":"nodeid" if "::" in selector else "filtered_file" if filtered else "file",
            "root_panel":"testbed" if cwd=="/testbed" else "named_repo"}

def concrete(p, cwd):
    if not isinstance(p, str) or not re.fullmatch(POS, p) or ".." in p.split("/"):
        return None
    return posixpath.normpath(posixpath.join(cwd, p))

def py_write(script, cwd):
    try: tree = ast.parse(script)
    except SyntaxError: return None
    names = {}
    writers = set()
    writes = []
    def path(n):
        if isinstance(n, ast.Constant): return concrete(n.value, cwd)
        if isinstance(n, ast.Name): return names.get(n.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Path" and len(n.args)==1:
            return path(n.args[0])
        return None
    def visit(statements):
        for n in statements:
            if isinstance(n, ast.ImportFrom) and n.module == "pathlib" and all(x.name == "Path" and not x.asname for x in n.names): continue
            if isinstance(n, ast.With):
                for context in n.items:
                    c = context.context_expr
                    if not (isinstance(c, ast.Call) and isinstance(c.func,ast.Name) and c.func.id=="open" and c.args and path(c.args[0]) and isinstance(context.optional_vars, ast.Name)): return False
                    mode=c.args[1].value if len(c.args)>1 and isinstance(c.args[1],ast.Constant) else "r" if len(c.args)==1 else ""
                    if c.keywords: return False
                    if mode in ("w","a","w+","r+"): writes.append(path(c.args[0]));writers.add(context.optional_vars.id)
                    elif mode not in ("r","rb"):return False
                if not visit(n.body):return False
                continue
            if not isinstance(n,(ast.Assign,ast.Expr,ast.Assert)):return False
            if isinstance(n,ast.Assign):
                if not all(isinstance(t,ast.Name) for t in n.targets):return False
                for t in n.targets:names[t.id]=path(n.value)
            for c in ast.walk(n):
                if not isinstance(c,ast.Call):continue
                if isinstance(c.func,ast.Name) and c.func.id in ("Path","print","len","str"):continue
                if not isinstance(c.func,ast.Attribute):return False
                method=c.func.attr
                if method in ("read","readlines","read_text","replace","strip","split","splitlines","join","index","find","count","startswith","endswith","format","encode","decode"):continue
                if method in ("write_text","write_bytes") and path(c.func.value):
                    writes.append(path(c.func.value));continue
                if method=="write" and isinstance(c.func.value,ast.Name) and c.func.value.id in writers:continue
                return False
        return True
    return sorted(set(writes)) if visit(tree.body) and writes else None

def classify(command):
    text=command.strip()
    cd=CD.match(text)
    cwd=cd[1] if cd else "/testbed"
    if not cwd.startswith("/"):return "unknown",[]
    cmd=text[cd.end():].strip() if cd else text
    # Literal here-document bodies are data. The footer has to end the entire shell command.
    h=re.fullmatch(r"(python(?:3(?:\.\d+)?)?(?:\s+-)?|cat\s+(?:>>|>)\s*("+POS+r"))\s+<<\s*['\"]?(\w+)['\"]?\s*\n(.*?)\n\3",cmd,re.S)
    if h:
        if h[2]:
            p=concrete(h[2],cwd)
            return ("write",[p]) if p else ("unknown",[])
        paths=py_write(h[4],cwd)
        return ("write",paths) if paths else ("unknown",[])
    if any(ch in cmd for ch in ("\n","$","\x60",">","<",";","&&","||","&")):return "unknown",[]
    try:
        parser=shlex.shlex(cmd,posix=True,punctuation_chars="|")
        parser.whitespace_split=True; parser.commenters=""
        groups=[[]]
        for token in parser:
            if token=="|":groups.append([])
            else:groups[-1].append(token)
    except ValueError:return "unknown",[]
    if any(not g for g in groups):return "unknown",[]
    if len(groups)==1:
        g=groups[0]
        if len(g)>=4 and g[0]=="sed" and g[1]=="-i" and re.fullmatch(r"s([/@|#]).*\1[gI0-9]*",g[2]) and len(g)==4:
            p=concrete(g[3],cwd)
            return ("write",[p]) if p else ("unknown",[])
        if g[0]=="touch" and len(g)==2:
            p=concrete(g[1],cwd);return ("write",[p]) if p else ("unknown",[])
    for g in groups:
        name=g[0]
        if name in {"cat","head","tail","pwd","ls","wc","nl","du","stat","diff","basename","dirname","which","echo"}:continue
        if name in {"grep","rg"} and not any(s.startswith(("--pre","--hostname-bin")) for s in g):continue
        if name=="find" and not any(s in ("-exec","-execdir","-delete","-ok","-okdir","-fprint","-fprintf","-fprint0","-fls") for s in g):continue
        if name=="sed" and len(g)>=3 and g[1]=="-n" and re.fullmatch(r"\d+(?:,\d+)?p",g[2]):continue
        if name=="git" and len(g)>=2 and g[1] in {"diff","show","status","log","ls-files","rev-parse"} and not any(s.startswith(("--output","--ext-diff","--textconv","--exec-path")) for s in g):continue
        return "unknown",[]
    return "read",[]

def policies(events, k, concurrent):
    any_unknown=concurrent or any(e["class"]=="unknown" for e in events)
    writes=sorted({p for e in events for p in e["paths"]})
    # Addresses underneath two apparent roots can alias in these histories.
    different_root=any(p.split("/")[1]!=k["path"].split("/")[1] for p in writes)
    special = lambda p: PurePosixPath(p).name in CONFIG
    def stem(p):
        s=PurePosixPath(p).stem.lower()
        return s.removeprefix("test_").removesuffix("_test")
    def auxiliary(p):
        name=PurePosixPath(p).name.lower()
        return ((name.startswith("test_") or name.endswith("_test.py")) and name.endswith(".py")) or PurePosixPath(p).suffix.lower() in (".md",".rst",".txt")
    opaque=any_unknown or different_root
    accept_name=not opaque and all(p!=k["path"] and not special(p) and stem(p)!=stem(k["path"]) for p in writes)
    accept_aux=not opaque and all(auxiliary(p) and p!=k["path"] and not special(p) for p in writes)
    return {"rerun_all":False,"reuse_all":True,"read_only":not any_unknown and not writes,
            "changed_stem":accept_name,"other_tests_or_docs":accept_aux},writes,any_unknown,different_root

def actions(messages):
    seq={};byid={}
    for i,m in enumerate(messages):
        if m["role"]=="assistant":
            batch=m.get("tool_calls") or []
            for c in batch:
                f=c.get("function") or {}; args=f.get("arguments") or {}
                try: args=json.loads(args) if isinstance(args,str) else args
                except ValueError:args={}
                cid=c.get("id")
                if cid:byid[cid]={"id":cid,"i":i,"parallel":len(batch)>1,"cmd":args.get("command") if f.get("name")=="bash" and isinstance(args,dict) else None}
        if m["role"]=="tool" and m.get("tool_call_id") in byid:seq[i]=byid[m["tool_call_id"]]
    return seq,byid

def main():
    cohort=read(RECEIPTS/"cohort.json")
    lock=read(RECEIPTS/"input-lock.json")
    for n in ("calls.gz","collect.py","cohort.json"):assert sha((RECEIPTS/n).read_bytes())==lock[n]
    items=collections.defaultdict(list)
    for row in read(RECEIPTS/"calls.gz"):
        k=key(row)
        if k:items[row["iid"]].append((row,k))
    forecasts=[];ct=collections.Counter();sealed_inputs={}
    for name,digest in cohort["source_files"].items():
        iid=Path(name).parent.name
        if iid not in items:continue
        raw=(UPSTREAM/name).read_bytes();assert sha(raw)==digest;sealed_inputs[name]=digest
        msgs=json.loads(raw)["messages"];user=next(m.get("content","") for m in msgs if m["role"]=="user")
        if "/testbed (this is the working directory" not in user and "working directory is /testbed" not in user:
            ct["missing_default"]+=len(items[iid]);continue
        seq,byid=actions(msgs);prev={}
        for row,k in sorted(items[iid],key=lambda u:u[0]["step"]):
            ct["qualifying_invocations"]+=1
            cmd=row["cmd"].strip(); old=prev.get(cmd);prev[cmd]=row
            if old is None:continue
            ct["consecutive_pairs"]+=1
            if terminal(old["visible"])[0]!="pass" or old["rc"]!=0:continue
            prior=seq[old["step"]];nxt=seq[row["step"]];assert prior["id"]==old["tool_call_id"] and nxt["id"]==row["tool_call_id"]
            start=old["step"];stop=nxt["i"]
            events=[];parallel=prior["parallel"] or nxt["parallel"]
            for c in byid.values():
                if not start<c["i"]<stop:continue
                parallel|=c["parallel"]
                successful=any(r["id"]==c["id"] and j<stop for j,r in seq.items())
                command=c["cmd"] or ""
                cls,paths=classify(command) if successful and c["cmd"] else ("unknown",[])
                events.append({"id":c["id"],"cmd_sha":sha(command.encode()),"class":cls,"paths":paths})
            pred,paths,opaque,roots=policies(events,k,parallel)
            forecasts.append({"iid":iid,"repo":row["repo"],"panel":row["panel"],"old_id":old["id"],"new_id":row["id"],"old_step":start,"new_step":row["step"],"test_key":k,"command_sha":sha(row["cmd"].encode()),"events":events,"parallel":parallel,"unclassified":opaque,"ambiguous_root":roots,"changed_paths":paths,"predictions":pred})
    put("predictions.gz",forecasts);put("inputs.json",{"frozen_panel":lock["calls.gz"],"sources":sealed_inputs,"n":len(forecasts),"counts":ct})
    put("forecast-seal.json",{n:sha((ROOT/n).read_bytes()) for n in ("PROTOCOL_RU.md","SCOPE_ADDENDUM_RU.md","observe.py","inputs.json","predictions.gz")})
    print(ct, len(forecasts))
if __name__=="__main__":main()

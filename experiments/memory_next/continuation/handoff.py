"""Deterministic action manifest. Reads only the solver-visible predecessor state."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / "repair"
SYSTEM = ("Continue fixing the issue in the existing working tree in /testbed. "
          "A predecessor already worked on this checkout. You have up to 8 model calls, including your final response. "
          "Use bash to inspect, edit and run relevant tests. Each command starts in /testbed, offline. "
          "Leave working-tree changes in place and answer briefly when done. Check claims against this checkout. "
          "Do not use git history or look for benchmark materials.")
LEGAL = re.compile(r"(?:[.][./])?[A-Za-z0-9_][\w./-]*[.](?:py|rst|txt|ini|md|json|cfg|toml|yaml|yml|c|h|sh)\b")
INSPECT = re.compile(r"(?:^|[;&|]\s*)\s*(?:cat|sed|grep|rg|head|tail|nl|less|more)\b")
TEST = re.compile(r"(?:^|[\s;&|(/])(?:pytest|py[.]test|tox|nosetests|unittest)(?=$|[\s;&|)/])|(?:^|\s)python\S*\s+setup[.]py\s+test\b")
TOOL = {"type":"function","function":{"name":"bash","description":"Run a local bash command or Python here-document in the repository. Output may be shortened. No network.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"],"additionalProperties":False}}}

def sha(b):
    return hashlib.sha256(b).hexdigest()

def write_json(p, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

def items(p):
    return [json.loads(s) for s in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

def normalize(s):
    return re.sub(r"\s+", " ", s.strip())

def clip(s,k):
    if len(s)<=k: return s
    return s[:k*2//3-8] + " [omitted] " + s[-(k//3-3):]

def ev(a):
    args=a.get("arguments","{}")
    try:
        parsed=json.loads(args) if isinstance(args,str) else args
        cmd=parsed.get("command","") if isinstance(parsed,dict) else ""
    except (ValueError,TypeError):
        cmd=""
    output=a.get("context_output","")
    m=re.match(r"Exit (-?\d+)\b",output)
    status=int(m[1]) if m else None
    return {"turn":a["turn"],"index":a["index"],"name":a["name"],"cmd":cmd,"status":status,"out":output,
            "executable":a["name"]=="bash" and status is not None}

def is_test(cmd):
    return any(bool(TEST.search(s)) for s in cmd.splitlines()[:1])

def one_line(item):
    return f't{item["turn"]}.{item["index"]} shell exit {item["status"]}: '+clip(normalize(item["cmd"]),160)

def payload(actions, diff):
    logs=[ev(a) for a in actions]
    files=[]; tests=[];failed=[];counts=Counter()
    for a in logs:
        if not a["executable"]:
            continue
        cmd=a["cmd"]
        counts[normalize(cmd)]+=1
        if is_test(cmd):
            tests.append(one_line(a))
        if a["status"]!=0:
            failed.append(one_line(a))
        # Restrict to explicit inspection commands with an observable success status.
        # Names from Python bodies, redirected outputs, and quoted search patterns are excluded.
        if a["status"]!=0:continue
        for segment in re.split(r"\s*(?:&&|\|\||[;|])\s*",cmd.split("\n",1)[0]):
            if not INSPECT.match(segment):continue
            try: ts=shlex.split(segment)
            except ValueError:continue
            opts=[x for x in ts[1:] if not x.startswith("-")]
            if ts[0] in {"sed","grep","rg"}: opts=opts[1:]
            for arg in opts:
                if LEGAL.fullmatch(arg) and not arg.startswith(("/tmp/","../")) and arg not in files:
                    files.append(arg)
    changed=[]
    for line in diff.decode("utf-8","replace").splitlines():
        if line.startswith("diff --git "):
            try: path=shlex.split(line)[-1].removeprefix("b/")
            except ValueError:continue
            if path not in changed:changed.append(path)
    repeats=[f"{n}x "+clip(cmd,135) for cmd,n in counts.items() if n>1]
    groups=[("Explicit file arguments in successful inspection commands", files[:12]),
            ("Test commands actually issued (status of outer shell)",tests[-6:]),
            ("Most recent nonzero shell commands",failed[-4:]),
            ("Files in saved working-tree patch", changed[:8]),
            ("Repeated normalized shell commands",repeats[:4])]
    block="\n".join(name+"\n"+("\n".join("- "+v for v in vals) if vals else "- none recorded") for name,vals in groups)
    last=[]
    for a in logs[-2:]:
        arg=a["cmd"] if a["name"]=="bash" else next((v.get("arguments","{}") for v in reversed(actions) if v["turn"]==a["turn"] and v["index"]==a["index"]),"{}")
        if not isinstance(arg,str):arg=json.dumps(arg,ensure_ascii=False)
        last.append(f't{a["turn"]}.{a["index"]} {a["name"]}\nArguments: {clip(arg,700)}\nObserved: {clip(a["out"],750)}')
    return "\n\n".join(last) or "(no previous actions recorded)",block

def create(iid):
    dest=ROOT/"handoffs"/iid
    hist=OLD/"runs"/iid/"brief"
    complete=read(hist/"complete.json")
    raw=(hist/"candidate.patch").read_bytes()
    assert len(raw)==complete["patch_bytes"] and sha(raw)==complete["patch_sha256"]
    original=read(hist/"prompt-01.json")
    assert len(original["messages"])==2 and original["messages"][1]["role"]=="user"
    actions=items(hist/"actions.jsonl")
    assert complete["arm"]=="brief" and complete["id"]==iid
    dest.mkdir(exist_ok=True,parents=True)
    (dest/"inherited.patch").write_bytes(raw)
    shutil.copyfile(hist/"actions.jsonl",dest/"previous_actions.jsonl") if (hist/"actions.jsonl").exists() else (dest/"previous_actions.jsonl").write_bytes(b"")
    latest,manifest=payload(actions,raw)
    common=original["messages"][1]["content"]+"\n\nHandoff from previous session. The current working tree already contains its saved patch. You have at most 8 model calls remaining.\nLast two observed tool actions:\n"+latest
    for key,val in [("common_user.txt",common),("manifest_only.txt","\n\nAction log from the previous session:\n"+manifest)]:
        (dest/key).write_bytes(val.encode("utf-8"))
    files={p.name:sha(p.read_bytes()) for p in sorted(dest.iterdir()) if p.is_file() and p.name!="input_lock.json"}
    write_json(dest/"input_lock.json",{"id":iid,"model":original["model"],"source_complete_sha256":sha((hist/"complete.json").read_bytes()),
               "source_first_prompt_sha256":sha((hist/"prompt-01.json").read_bytes()),"previous_final_call_count":complete["calls"],
               "files":files})
    return dest

if __name__=="__main__":
    for iid in sorted({i for i,_ in read(ROOT/"assignments.json")}):
        if (OLD/"runs"/iid/"brief"/"complete.json").exists():
            create(iid)


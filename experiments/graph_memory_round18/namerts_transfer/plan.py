"""Use only official candidate SHA metadata, Git trees and package versions for cohort construction."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from owners import analyze

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parents[1]/"graph_memory_round17/namer_ts"
CACHE=Path("D:/CodexResearch/x20-r18-owner-transfer")
RELEASE=Path("D:/CodexResearch/x20-r17-namerts")
GIT=RELEASE/"loguru";PKG=RELEASE/"NameRTS";PY=RELEASE/"runtime/Scripts/python.exe"
VERSION="f1acdae0f2b2d1ed6e3e2956d510db49bb7c276f"
BAD=re.compile(r"(?:\bCVE-\d|security|vulnerab|injection|malicious|exploit|traceback leak|path traversal)",re.I)
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.name.endswith(".gz") else b)
def put(p,v):
    b=json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return p.write_bytes(gzip.compress(b,mtime=0) if p.name.endswith(".gz") else b)
def git(*args,where=GIT):return subprocess.check_output(["git","-c","core.autocrlf=false",*args],cwd=where)
def testfiles(commit):
    return {x for x in git("ls-tree","-r","--name-only",commit,"tests").decode().splitlines() if re.fullmatch(r"tests/test_[^/]+\.py",x)}
def features(parent,current):
    status=git("diff","--no-renames","--name-status",parent,current).decode().splitlines()
    modules={};fallback=[];edited=[]
    for line in status:
        mode,p=line.split("\t",1)
        if re.fullmatch(r"tests/test_[^/]+\.py",p):edited.append(p);continue
        if p.startswith("loguru/") and p.endswith(".py"):
            if mode!="M":
                fallback.append([mode,p]);continue
            a=git("show",parent+":"+p);b=git("show",current+":"+p)
            try:work=analyze(a.decode(),b.decode())
            except (UnicodeError,SyntaxError):fallback.append(["unparseable",p]);continue
            modules[p]={"old_sha":sha(a),"new_sha":sha(b),"change":work}
        elif (p.startswith("tests/") and p.endswith(".py")) or p in ("pyproject.toml","pytest.ini","setup.cfg","tox.ini","conftest.py") or p.startswith("loguru/"):
            fallback.append([mode,p])
    return {"modules":modules,"force_all":fallback,"edited_tests":sorted(edited),"all_git_changes":status}
def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    manifest_path="dataset/commit_pairs_loguru.json";raw=git("show",VERSION+":"+manifest_path,where=PKG)
    assert json.loads(raw)==load(PKG/manifest_path)
    full=json.loads(raw);target=[r for r in full if r[3]];assert len(target)==50
    prior=load(OLD/"transfer-plan.json")["pairs"];prev={v for r in prior for v in (r["current"],r["parent"],r["direct_parent"])}
    ordered=sorted(target,key=lambda r:sha(("owner-r18|"+r[2]).encode()))
    flow=[];selected=[];known=[]
    for direct,base,c,_flag in ordered:
        message=git("log","-1","--format=%s",c).decode().strip()
        reason="previous_sha" if prev.intersection((direct,base,c)) else "excluded_topic" if BAD.search(message) else None
        if reason is None and len(selected)<6:chosen=True
        else:chosen=False
        row={"current":c,"true_parent":base,"direct_parent":direct,"rank_key":sha(("owner-r18|"+c).encode()),
             "eligibility":reason or "candidate","selected":chosen}
        flow.append(row)
        if not chosen:continue
        parents=git("show","-s","--format=%P",c).decode().split()
        assert direct in parents
        available=sorted(testfiles(base)&testfiles(c),key=lambda p:sha(("file-r18|"+c+"|"+p).encode()))
        tests=available[:20]
        selected.append({**row,"subject":message,"pool":available,"tests":tests,"test_sha":{p:sha(git("show",base+":"+p)) for p in tests},**features(base,c)})
    assert len(selected)==6 and all(not prev.intersection((p["current"],p["true_parent"],p["direct_parent"])) for p in selected)
    for p in prior:
        known.append({"current":p["current"],"true_parent":p["parent"],"module":p["path"],**features(p["parent"],p["current"])})
    plan={"roster_sha":sha(raw),"manifest_file":manifest_path,"official_commit":VERSION,"old_plan_sha":sha((OLD/"transfer-plan.json").read_bytes()),
          "old_shas":sorted(prev),"target_rows":len(target),"flow":flow,"cohort":selected,"known_calibration":known,
          "python":subprocess.check_output([str(PY),"--version"]).decode().strip(),
          "environment":subprocess.check_output(["uv","pip","freeze","--python",str(PY)]).decode().splitlines()}
    put(ROOT/"plan.json",plan)
    put(ROOT/"plan-lock.json",{n:sha((ROOT/n).read_bytes()) for n in ("PROTOCOL_RU.md","plan.py","owners.py","worker.py","forecast.py","plan.json")})
    print([(p["current"][:8],len(p["pool"]),p["subject"],list(p["modules"]),p["force_all"]) for p in selected])
if __name__=="__main__":main()

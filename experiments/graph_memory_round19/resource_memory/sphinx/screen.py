from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
ROOT=Path(__file__).resolve().parent
PKG=Path("D:/CodexResearch/x20-r17-namerts/NameRTS")
V="f1acdae0f2b2d1ed6e3e2956d510db49bb7c276f"
def sha(b):return hashlib.sha256(b).hexdigest()
def read(row):
    d,b,c,_=row;record={"direct_parent":d,"base":b,"current":c}
    url=f"https://api.github.com/repos/sphinx-doc/sphinx/compare/{b}...{c}"
    record["url"]=url
    req=urllib.request.Request(url,headers={"User-Agent":"graph-memory-academic-screen","Accept":"application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req,timeout=35) as r:raw=r.read();data=json.loads(raw)
    except (OSError,ValueError) as e:
        return {**record,"status":"metadata_unavailable","message":str(e)}
    changes=[(f["status"],f["filename"]) for f in data.get("files",[])];assert data["base_commit"]["sha"]==b
    seen=data.get("commits",[]);assert seen and seen[-1]["sha"]==c
    subject=seen[-1]["commit"]["message"].splitlines()[0]
    candidate=[p for s,p in changes if s=="modified" and (p=="pyproject.toml" or p.startswith("sphinx/") and p.endswith(".pyi") or p.startswith(("tests/roots/","tests/fixtures/")))]
    excluded=[p for s,p in changes if p=="conftest.py" or p.startswith("tests/") and p.endswith("/conftest.py") or p.startswith("sphinx/") and p.endswith(".py") or s=="added" and p.endswith((".py",".sh",".ps1",".bat"))]
    reason="incomplete_files" if len(changes)>=300 else "excluded_topic" if re.search(r"CVE-|security|vulnerab|exploit|injection",subject,re.I) else "no_target_resource" if not candidate else "other_runtime_changes" if excluded else "eligible"
    return {**record,"blob_sha":sha(raw),"status":reason,"subject":subject,"resources":candidate,"other_runtime":excluded,"files":changes}
def main():
    r=subprocess.check_output(["git","show",V+":dataset/commit_pairs_sphinx.json"],cwd=PKG)
    rows=sorted([x for x in json.loads(r) if x[3]],key=lambda x:sha(("r19-sphinx|"+x[2]).encode()))
    assert len(rows)==50
    with ThreadPoolExecutor(max_workers=3) as pool:selected=list(pool.map(read,rows[:12]))
    output={"roster_sha":sha(r),"protocol_sha":sha((ROOT/"SCREEN_RU.md").read_bytes()),"script_sha":sha(Path(__file__).read_bytes()),"candidates":selected}
    (ROOT/"screen.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    print([(s["current"][:8],s["status"]) for s in selected])
if __name__=="__main__":main()

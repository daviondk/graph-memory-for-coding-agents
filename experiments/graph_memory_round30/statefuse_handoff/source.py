"""Fetch only the public StateFuse Python modules and example needed for the lab."""
import hashlib,json
from pathlib import Path
import subprocess
REV="21b62cabc990997e163ff77ebf1c386154a0a977"
UPSTREAM="https://api.github.com/repos/nZiben/statefuse"
CACHE=Path("D:/CodexResearch/x20-r30-statefuse")/REV
HERE=Path(__file__).resolve().parent
def fetch(url):
    return subprocess.check_output(["curl.exe","--fail","--silent","--show-error","--location","--max-time","30",url])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def acquire():
    tree=json.loads(fetch(UPSTREAM+"/git/trees/"+REV+"?recursive=1"))
    rows={}
    for item in tree["tree"]:
        name=item["path"]
        if item["type"]!="blob" or not (name.startswith("src/statefuse/") and name.endswith(".py") or name in ("pyproject.toml","examples/02_branch_diverge_merge.py","tests/test_core_records.py","tests/test_view_projection.py")):continue
        path=(CACHE/name).resolve();assert path.is_relative_to(CACHE.resolve())
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes(fetch("https://raw.githubusercontent.com/nZiben/statefuse/"+REV+"/"+name))
        raw=path.read_bytes();assert hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()==item["sha"]
        rows[name]=sha(path)
    (HERE/"source-lock.json").write_text(json.dumps({"revision":REV,"files":rows},sort_keys=True,indent=2)+"\n",encoding="utf8")
if __name__=="__main__":acquire()

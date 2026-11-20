"""Fetch pinned passive source artifacts. No package code is executed."""
import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent
PACKAGES = "more-itertools boltons fonttools pint svgwrite plotnine humanize wcwidth".split()
CACHE = Path("D:/CodexResearch/x20-round7-wheel-cache")
def fetch(url):
    for i in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent":"GraphMemoryResearch/1.0"}),timeout=45) as f:
                return f.read()
        except OSError:
            if i == 2: raise
            time.sleep(1 + i)
def choose(project):
    source = "https://pypi.org/pypi/" + project + "/json"
    data = json.loads(fetch(source))
    candidates = []
    for tag, files in data["releases"].items():
        try:
            version = Version(tag)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease or version.is_postrelease or version.local:
            continue
        wheels = sorted((f for f in files if f["filename"].endswith("-none-any.whl")
                         and not f["yanked"] and f["upload_time_iso_8601"] < "2025-01-01"),key=lambda f:f["filename"])
        if wheels:
            f = wheels[0]
            candidates.append((version,dict(project=project,version=tag,name=f["filename"],url=f["url"],
                uploaded=f["upload_time_iso_8601"], sha256=f["digests"]["sha256"],source=source)))
    return [row for _,row in sorted(candidates,key=lambda v:v[0])[-6:]]
def download(row):
    dest=CACHE/row["name"]
    data=dest.read_bytes() if dest.exists() else fetch(row["url"])
    assert hashlib.sha256(data).hexdigest()==row["sha256"],dest
    if not dest.exists():dest.write_bytes(data)
if __name__ == "__main__":
    CACHE.mkdir(parents=True,exist_ok=True)
    parser=argparse.ArgumentParser();parser.add_argument("--select",action="store_true");args=parser.parse_args()
    manifest=ROOT/"sources.json"
    if args.select:
        rows = [row for series in ThreadPoolExecutor(6).map(choose,PACKAGES) for row in series]
        assert not manifest.exists()
        manifest.write_text(json.dumps(rows,indent=2)+"\n",encoding="utf8")
    rows=json.loads(manifest.read_bytes())
    list(ThreadPoolExecutor(6).map(download,rows))
    print("Verified",len(rows),"source wheels from", len({r["project"] for r in rows}),"projects.")

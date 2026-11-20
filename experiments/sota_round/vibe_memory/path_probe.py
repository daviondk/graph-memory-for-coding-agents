"""Query exact candidate paths in immutable target snapshots, using public base commits."""
import hashlib
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pyarrow.parquet as pq
from fetch_history import BASE

ROOT=Path(__file__).resolve().parent
EXT="py|pyi|js|jsx|mjs|cjs|ts|tsx|go|rs|kt|kts|swift|java|php|scala|c|cc|cpp|h|hpp|css|html|xml|yml|yaml|json|toml|ini|cfg|txt|md|rst|sh|gradle|properties|mod|sum|lock|rb|sql"
PATH=re.compile(r"(?<![\w./-])((?:\.{1,2}/|/)?(?:[\w@.+-]+/)*[\w@+-][\w@.+-]*\.(?:"+EXT+r"))(?![\w./-])",re.I)
BLOCK={"patch.txt",".git","__pycache__",".venv","venv","node_modules","site-packages","dist-packages",".cache"}


def extract(body,repo):
    unique={}
    for m in PATH.finditer(body):
        name=m[1]
        if name.startswith("/"):
            pieces=name[1:].split("/",1)
            if len(pieces)!=2 or pieces[0].lower() not in {"testbed",repo.rsplit("/",1)[-1].lower()}:
                continue
            name=pieces[1]
        name=name.removeprefix("./")
        if name.startswith(("a/","b/")):
            name=name[2:]
        parts=PurePosixPath(name).parts
        if not parts or any(t.lower() in BLOCK or t==".." for t in parts):
            continue
        unique[name]=None
        if len(unique)==3:
            break
    return list(unique)


def status(url):
    req=Request(url,headers={"User-Agent":"VibeMemBench-archived-path-check","Range":"bytes=0-0"})
    for attempt in range(3):
        try:
            with urlopen(req,timeout=15) as resp:
                resp.read(1)
                return int(resp.status)
        except HTTPError as err:
            if err.code not in (429,500,502,503,504) or attempt==2:
                return err.code
        except (OSError,URLError):
            if attempt==2:
                return 0
        time.sleep(2+2*attempt)
    return 0


def main():
    targets={t["instance_id"]:t for t in pq.read_table(BASE/"benchmark"/"test.parquet",
             columns=["instance_id","repo","base_commit","language"]).to_pylist()}
    requests={}
    rows=[]
    with ZipFile(ROOT/"stage_outputs.zip") as z:
        for name in sorted(z.namelist()):
            if not name.endswith("memory.txt"):
                continue
            method,_,q,_=name.split("/")
            t=targets[q]
            content=z.read(name).decode("utf8").partition("\n")[2]
            hits=extract(content,t["repo"])
            paths=[]
            for path in hits:
                url=f"https://raw.githubusercontent.com/{t['repo']}/{t['base_commit']}/{quote(path,safe='/')}"
                requests[url]=None
                paths.append({"path":path,"url":url})
            rows.append({"instance_id":q,"method":method,"repo":t["repo"],"commit":t["base_commit"],"paths":paths})
    print("Frozen text extraction",len(rows),"items",len(requests),"distinct URLs",flush=True)
    with ThreadPoolExecutor(max_workers=15) as pool:
        responses=dict(zip(requests,pool.map(status,requests)))
        commit_urls={}
        for row in rows:
            if row["paths"] and all(responses[x["url"]] in (404,410) for x in row["paths"]):
                key=(row["repo"],row["commit"])
                commit_urls[key]=f"https://github.com/{key[0]}/commit/{key[1]}"
        commits=dict(zip(commit_urls,pool.map(status,commit_urls.values())))
    for row in rows:
        commit_status=commits.get((row["repo"],row["commit"]))
        row["commit_page_status_if_checked"]=commit_status
        for ref in row["paths"]:
            s=responses[ref["url"]]
            ref["status"]=s
            ref["exists"]=True if s in (200,206) else (False if s in (404,410) and
                (commit_status in (200,206) or any(responses[x["url"]] in (200,206) for x in row["paths"])) else None)
    (ROOT/"path_rows.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf8")
    summary={"protocol_sha256":hashlib.sha256((ROOT/"path-protocol.md").read_bytes()).hexdigest(),
             "stage_zip_sha256":hashlib.sha256((ROOT/"stage_outputs.zip").read_bytes()).hexdigest(),
             "unique_raw_urls":len(requests),"raw_http":dict(Counter(responses.values())),
             "commit_http":dict(Counter(commits.values())),"by_method":{}}
    for method in sorted({r["method"] for r in rows}):
        rr=[r for r in rows if r["method"]==method]
        refs=[p for r in rr for p in r["paths"]]
        x={"all":len(rr),"with_candidate_path":sum(bool(r["paths"]) for r in rr),
           "with_confirmed_path":sum(any(p["exists"] is True for p in r["paths"]) for r in rr),
           "with_unknown_path":sum(any(p["exists"] is None for p in r["paths"]) for r in rr),
           "unique_paths_per_item_sum":len(refs),"confirmed_paths":sum(p["exists"] is True for p in refs),
           "unknown_paths":sum(p["exists"] is None for p in refs)}
        summary["by_method"][method]=x
    (ROOT/"path_results.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    print(json.dumps(summary,indent=2),flush=True)


if __name__=="__main__":
    main()

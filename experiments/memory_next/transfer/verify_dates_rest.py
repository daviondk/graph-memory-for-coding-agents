"""Independent public REST spot-check for reconstructed dates; sample fixed by hash."""
import concurrent.futures
import csv
import hashlib
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parent

def get_rows(name):
    with (ROOT/name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def selection(rows, k, field):
    order = lambda r: hashlib.sha256(("clock-check-20261116/" + r[field]).encode()).digest()
    return sorted(rows, key=order)[:k]

def fetch(job):
    label,url,stored,field=job
    out={"type":label,"url":url,"stored":stored}
    try:
        req = urllib.request.Request(url,headers={"Accept":"application/vnd.github+json","User-Agent":"agent-memory-chronology-research"})
        with urllib.request.urlopen(req,timeout=18) as response:
            raw = response.read()
        obj=json.loads(raw)
        out["github"]=obj.get(field)
        out["response_sha256"]=hashlib.sha256(raw).hexdigest()
        out["same"]=out["github"]==stored
    except Exception as e:
        out["error"]=str(e)
    return out

if __name__ == "__main__":
    jobs=[]
    for h in selection([x for x in get_rows("history_times_full.csv") if x["merged"]], 10, "id"):
        jobs.append(("source merge","https://api.github.com/repos/"+h["repo"]+"/pulls/"+h["pr"],h["merged"],"merged_at"))
    for q in selection(get_rows("query_times_lite.csv"), 6, "target"):
        jobs.append(("target PR opened","https://api.github.com/repos/"+q["repo"]+"/pulls/"+q["target_pr"],q["pr_open"],"created_at"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        receipts=list(executor.map(fetch,jobs))
    (ROOT/"rest_spotcheck.json").write_text(json.dumps(receipts,ensure_ascii=False,indent=1),encoding="utf-8")
    print("checked",len(receipts),"exact",sum(r.get("same",False) for r in receipts),"errors",sum("error" in r for r in receipts))


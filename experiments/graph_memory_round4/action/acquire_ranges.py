"""Recover range arguments from the original tool call, matched to R3's independently checked tool-call id."""
import concurrent.futures
import gzip
import hashlib
import json
import time
import urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent
OLD = D.parents[1] / "graph_memory_round3"
SEARCH = {"A":"real_swe", "B":"real_swe_followup"}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def write(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=True,indent=1),encoding="utf8")

def get(job):
    panel, issue, prior, keys = job
    dest = D/"ranges"/(issue+".json")
    if dest.is_file(): return json.loads(dest.read_bytes())["status"]
    error = None
    for j in range(3):
        try:
            request=urllib.request.Request(prior["url"],headers={"User-Agent":"R4-agent-memory-confirmation"})
            with urllib.request.urlopen(request,timeout=75) as r: raw=r.read(48*1024**2+1)
            checksum = digest(raw)
            assert checksum==prior["source_sha256"]
            source=json.loads(raw)
            del raw
            found={}
            for step in source["history"]:
                if step.get("role")!="assistant":continue
                for tc in step.get("tool_calls",[]) or []:
                    key=digest(str(tc["id"]).strip().encode())
                    if key not in keys:continue
                    args=tc["function"]["arguments"]
                    if isinstance(args,str):args=json.loads(args)
                    assert args["command"]=="view" and isinstance(args.get("path"),str)
                    item=keys[key]
                    assert item[1]==args["path"].removeprefix("/testbed/").removeprefix("./")
                    val=args.get("view_range")
                    found[item[0]]=val
            assert len(found)==len(keys)
            write(dest,dict(issue=issue,panel=panel,status="ok",source_sha256=checksum,url=prior["url"],ranges=found))
            return "ok"
        except (OSError,ValueError,KeyError,AssertionError) as exc:
            error=type(exc).__name__+":"+str(exc)[:100]
            time.sleep(1)
    write(dest,dict(issue=issue,panel=panel,status="error",url=prior["url"],error=error))
    return error

def main():
    (D/"ranges").mkdir(exist_ok=True)
    jobs=[]
    for panel,folder in SEARCH.items():
        root=OLD/folder
        receipts={r["id"]:r for r in json.loads((root/"receipts.json").read_bytes()) if r["status"]=="ok"}
        for path in sorted(root.glob("source_*.jsonl.gz")):
            with gzip.open(path,"rt",encoding="utf8") as f:
                for line in f:
                    o=json.loads(line); issue=o["instance"]
                    keys={q[9]:(q[0],q[3]) for q in o["pair_projection"] if q[2]=="view"}
                    jobs.append((panel,issue,receipts[issue],keys))
    assert len({j[1] for j in jobs})==len(jobs)==293
    write(D/"selection.json",[{k:v for k,v in zip(("panel","issue","sha256","view_call_ids"),(j[0],j[1],j[2]["source_sha256"],len(j[3])))} for j in jobs])
    from collections import Counter
    freq=Counter()
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        futures=[pool.submit(get,job) for job in jobs]
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            freq[f.result()]+=1
            if n%20==0:print(n,dict(freq),flush=True)
    write(D/"acquisition.json",dict(freq))
    print(freq,flush=True)

if __name__=="__main__":
    main()

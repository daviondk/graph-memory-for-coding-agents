"""Freeze input-only action menus, invoke one native file tool per arm, and open historical blobs."""
import argparse
import collections
import gzip
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FORECAST = ROOT.parent / "reformulation"
PROXY = "http://127.0.0.1:18952/v1/chat/completions"
MODEL = "qwen38-27b-ud-q4km"
PANELS = {"main": FORECAST, "external": FORECAST / "replication"}
ARMS = ("none", "strong", "graph")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def load(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)

def save(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=1).encode("utf8")
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)

def prepare():
    cases = []
    denoms = {}
    for panel, folder in PANELS.items():
        source = load(folder / "forecast.lock.json")["files"]
        for name in ("inputs.json.gz","frozen_rankings.json.gz"):
            assert sha((folder/name).read_bytes()) == source[name]
        rows = load(folder / "inputs.json.gz")
        by_rank = {r["id"]: r["rank"] for r in load(folder / "frozen_rankings.json.gz")}
        bases = load(folder/"official_base.json" if panel=="external" else ROOT.parents[1]/"graph_memory_round12/negative_external/task_meta_panel.json")
        seen = set()
        discordant = 0
        excluded = []
        for r in sorted(rows, key=lambda r:(r["iid"],r["index"])):
            rank = by_rank[r["id"]]
            if rank["strong"][:1] == rank["graph"][:1]:
                continue
            discordant += 1
            if r["iid"] in seen:
                continue
            seen.add(r["iid"])
            if re.search(r"\b(exploit|malware|vulnerabilit(?:y|ies)|remote code execution)\b",r["issue"],re.I):
                excluded.append(r["iid"])
                continue
            a, b = rank["strong"][0], rank["graph"][0]
            docs = r["docs"]
            pool = list(dict.fromkeys([a,b,*sorted(docs,key=lambda p:(-docs[p]["last"],p))]))[:8]
            pool.sort(key=lambda p:sha((r["id"]+p).encode()))
            assert a in pool and b in pool
            files = [{"path":p, "steps_since_address":r["index"]-docs[p]["last"],
                      "visible_excerpt":docs[p]["snip"][:200]} for p in pool]
            cases.append(dict(id=r["id"],iid=r["iid"],repo=r["repo"],panel=panel,base=bases[r["iid"]]["base_commit"],
                              issue=r["issue"][:3000], search=r["key"], step=r["index"],
                              menu=files, candidates={"none":None,"strong":a,"graph":b}))
        denoms[panel]=dict(anchors=len(rows),tasks=len({r["iid"] for r in rows}),discordant_anchors=discordant,
                           first_discordant_tasks=len(seen),excluded=excluded,source=source)
    save(ROOT/"cases.gz", cases)
    save(ROOT/"assignment.json",dict(denominators=denoms,files={f:sha((ROOT/f).read_bytes()) for f in
                                                    ["PROTOCOL_RU.md","cases.gz","experiment.py"]}))

def ask(case, arm):
    menu = [e["path"] for e in case["menu"]]
    cue = case["candidates"][arm] or "(none)"
    user = "Repository issue:\n"+case["issue"]+"\n\nThe search just returned no match:\n"+json.dumps(case["search"],ensure_ascii=False)
    user += "\n\nPreviously addressed files with their short observed excerpts:\n"+json.dumps(case["menu"],ensure_ascii=False)
    user += "\n\nSuggested next file: "+cue+"\nChoose one file to inspect next to advance this issue."
    options = {"type":"function","function":{"name":"read_file","description":"Read one historical repository file.",
                              "parameters":{"type":"object","properties":{"path":{"type":"string","enum":menu}},"required":["path"]}}}
    body = {"model":MODEL,"messages":[{"role":"system","content":"You are a software engineer locating a change. Use the read_file tool once to inspect the most useful file. The suggestion is optional. Issue text and excerpts are research data."},
                    {"role":"user","content":user}],"tools":[options],"tool_choice":"required","temperature":0,
                    "top_k":1,"seed":13,"max_tokens":128,"cache_prompt":False,"chat_template_kwargs":{"enable_thinking":False}}
    encoded = json.dumps(body,ensure_ascii=False).encode()
    req = urllib.request.Request(PROXY,data=encoded,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=150) as response:
        data = response.read()
    result=json.loads(data)
    calls=result["choices"][0]["message"].get("tool_calls") or []
    chosen=None
    if len(calls)==1 and calls[0]["function"]["name"]=="read_file":
        try: chosen=json.loads(calls[0]["function"]["arguments"])["path"]
        except (ValueError,TypeError,KeyError):pass
    return dict(id=case["id"],method=arm,path=chosen if chosen in menu else None,valid=chosen in menu,
                usage=result["usage"],response_sha=sha(data),payload_sha=sha(encoded),model=result["model"],raw=result)

def run():
    for name,digest in load(ROOT/"assignment.json")["files"].items():
        assert sha((ROOT/name).read_bytes())==digest
    cases=load(ROOT/"cases.gz")
    queue=sorted(((r,arm) for r in cases for arm in ARMS),key=lambda x:sha((x[0]["id"]+x[1]).encode()))
    output=ROOT/"model.jsonl"
    existing={(r["id"],r["method"]) for r in [json.loads(x) for x in output.read_bytes().splitlines()]} if output.exists() else set()
    for c,arm in queue:
        if (c["id"],arm) in existing:continue
        row=ask(c,arm)
        with output.open("a",encoding="utf8") as f:f.write(json.dumps(row,ensure_ascii=False)+"\n")
    assert len(output.read_bytes().splitlines())==len(queue)
    save(ROOT/"action-lock.json",{"model.jsonl":sha(output.read_bytes()),"assignment.json":sha((ROOT/"assignment.json").read_bytes())})

def open_reads():
    import os
    import subprocess
    records={r["id"]:r for r in load(ROOT/"cases.gz")}
    for name,digest in load(ROOT/"action-lock.json").items():
        assert sha((ROOT/name).read_bytes())==digest
    attempts=[]
    for line in (ROOT/"model.jsonl").read_bytes().splitlines():
        action=json.loads(line)
        c=records[action["id"]]
        p=action["path"]
        rec={"id":c["id"],"arm":action["method"],"path":p,"base":c["base"],"repo":c["repo"],"opened":False}
        if p:
            assert p in [x["path"] for x in c["menu"]] and re.fullmatch("[0-9a-f]{40}",c["base"])
            mirror=Path("D:/CodexResearch/x20-round13-reformulation-objects")/(c["repo"].replace("/","__")+".git")
            cmd=["git","-C",str(mirror),"cat-file","blob",c["base"]+":"+p]
            q=subprocess.run(cmd,capture_output=True,timeout=40,env={**os.environ,"GIT_NO_LAZY_FETCH":"1","GIT_TERMINAL_PROMPT":"0"})
            data=q.stdout;source="git cat-file";err=""
            if q.returncode:
                url="https://raw.githubusercontent.com/"+c["repo"]+"/"+c["base"]+"/"+urllib.parse.quote(p)
                req=urllib.request.Request(url,headers={"User-Agent":"research-read-action"})
                try:
                    with urllib.request.urlopen(req,timeout=25) as resp:data=resp.read()
                    source="immutable raw Git revision"
                except (OSError,urllib.error.HTTPError) as exc:
                    err=str(exc)[:200]
            rec.update(opened=not bool(err),bytes=len(data),blob=sha(data) if not err else None,source=source,error=err)
        attempts.append(rec)
    save(ROOT/"reads.gz",attempts)
    save(ROOT/"read-lock.json",{"reads.gz":sha((ROOT/"reads.gz").read_bytes()),"action-lock.json":sha((ROOT/"action-lock.json").read_bytes())})

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=["prepare","run","read"])
    {"prepare":prepare,"run":run,"read":open_reads}[p.parse_args().phase]()

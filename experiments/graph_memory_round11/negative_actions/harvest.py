"""Acquire immutable public SWE-agent trajectories and project only tool inputs and observations."""
import concurrent.futures
import collections
import difflib
import gzip
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent
W = D.parents[1]
REPOS = {"sympy/sympy","matplotlib/matplotlib","scikit-learn/scikit-learn","astropy/astropy","sphinx-doc/sphinx"}
EXCLUDE = re.compile(r"(?i)\b(vulnerability|exploit|XSS|CVE-\d+|SQL injection|remote code execution|path traversal)\b")
def get(p): return json.loads(p.read_bytes())
def save(p,obj): p.write_text(json.dumps(obj,ensure_ascii=True,indent=1),encoding="utf8")
def sha(data): return hashlib.sha256(data).hexdigest()
def read_rows(p):
    with gzip.open(p,"rt",encoding="utf8") as f: yield from map(json.loads,f)
def collect_roster():
    tasks=[]; all_counts={}
    for name, folder, pattern in [("Kimi-transfer",W/"graph_memory_round5/action_transfer","source_[0-7].gz"),("Kimi-writer",W/"graph_memory_round5/writer","source_[0-7].jsonl.gz"),("Claude",W/"graph_memory_round6/version/external","source.gz")]:
        recs=get(folder/("roster_lock.json" if name=="Claude" else "receipts.json"))
        lookup={r["id"]:r for r in (recs["manifest"] if name=="Claude" else recs)}
        ct=collections.Counter()
        for source in sorted(folder.glob(pattern)):
            for q in read_rows(source):
                ct["all"]+=1
                if q["official_repo"] not in REPOS: ct["out_of_scope_repo"]+=1;continue
                if EXCLUDE.search(q["issue"]):ct["out_of_scope_topic"]+=1;continue
                iid=q["instance"];r=lookup[iid]
                tasks.append(dict(panel=name,iid=iid,repo=q["official_repo"],base=q["base_commit"],url=r["url"],sha=r.get("sha") or r["sha256"], projected_actions=len(q["events"])))
                ct["included"]+=1
        all_counts[name]=ct
    if len(set(r["iid"] for r in tasks))!=len(tasks): raise ValueError("population overlaps")
    return tasks,all_counts
def get_text(txt):
    if isinstance(txt,str):return txt
    return "\n".join(x["text"] for x in (txt or []) if x.get("type")=="text")
def clean(s):return (s or "").strip().replace("\r\n","\n")
def load_one(q):
    home=D/"observations";home.mkdir(exist_ok=True)
    out=home/(q["iid"]+".json.gz")
    if out.exists():return {"id":q["iid"],"status":"existing","sha":sha(out.read_bytes())}
    for attempt in range(3):
        try:
            with urllib.request.urlopen(q["url"],timeout=45) as resp:b=resp.read(52*1024**2+1)
            if sha(b)!=q["sha"]:raise ValueError("native_sha")
            s=json.loads(b); hist=[]; current=None
            for item in s["history"]:
                if item["role"]=="assistant":
                    current=None
                    if "action" in item:
                        current=[clean(item["action"]),item.get("tool_calls") or [],[]]
                        hist.append(current)
                if item["role"]=="tool" and current is not None:current[2].append(item)
            trs=s["trajectory"]; aligned={}
            for a,c,n in difflib.SequenceMatcher(a=[clean(i.get("action")) for i in trs], b=[v[0] for v in hist],autojunk=False).get_matching_blocks():
                for k in range(n):aligned[a+k]=hist[c+k]
            projected=[]
            for k,step in enumerate(trs):
                h=aligned.get(k)
                if h is None or len(h[1])!=1 or len(h[2])!=1 or h[2][0].get("tool_call_ids")!=[h[1][0]["id"]]:
                    projected.append(None);continue
                tool=h[1][0]["function"];args=tool["arguments"]
                try:args=json.loads(args) if isinstance(args,str) else args
                except ValueError:args={}
                if not isinstance(args,dict):args={}
                raw=step.get("observation","");shown=get_text(h[2][0]["content"])
                # Mostly retain small outputs for negatives/errors. Large responses only need an integrity hash.
                projected.append({"tool":tool["name"],"args":args,"cwd":step.get("state",{}).get("working_dir"),"raw":raw if len(raw)<3500 else None,"seen":shown if len(shown)<3500 else None,"raw_len":len(raw),"seen_len":len(shown),"raw_sha":sha(raw.encode()),"seen_sha":sha(shown.encode())})
            block={"source":q,"steps":projected}
            out.write_bytes(gzip.compress(json.dumps(block,ensure_ascii=True,separators=(",",":")).encode(),compresslevel=4,mtime=0))
            return {"id":q["iid"],"status":"ok","sha":sha(out.read_bytes()),"steps":len(trs),"aligned":len(aligned),"url":q["url"]}
        except (OSError,ValueError,KeyError) as ex:
            if attempt==2:return {"id":q["iid"],"status":"error","error":str(ex)[:230]}
            time.sleep(1+attempt)
if __name__=="__main__":
    roster,counts=collect_roster()
    save(D/"roster.json",roster)
    save(D/"roster_lock.json",{"protocol":sha((D/"PROTOCOL_RU.md").read_bytes()),"roster":sha((D/"roster.json").read_bytes()),"counts":counts,"acquisition":sha(Path(__file__).read_bytes())})
    print("locked",len(roster),counts,flush=True)
    with concurrent.futures.ThreadPoolExecutor(9) as pool:
        collected=[]
        for n,r in enumerate(pool.map(load_one,roster),1):
            collected.append(r)
            if n%20==0:print("collected",n,collections.Counter(x["status"] for x in collected),flush=True)
    save(D/"receipts.json",collected);print("final",collections.Counter(x["status"] for x in collected),flush=True)

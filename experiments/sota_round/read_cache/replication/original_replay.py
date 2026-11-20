"""Replay structured Claude Code tool events; never execute a tool from a trace."""
import argparse
from collections import Counter,OrderedDict
from dataclasses import dataclass
from datetime import datetime,timezone
import gzip
import hashlib
import json
import posixpath
import re
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ARMS=("lru","ttl1","ttl3","ttl10","flush","selective","write_through")
READONLY={"Read","Glob","Grep","TodoWrite"}
MUTATE={"Write","Edit","MultiEdit"}
CLONE=re.compile(r"\bgit\s+clone\s+(?:[^;&\n]+?\s+)?(?:https?://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+)",re.I)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def emit(f,obj):
    f.write(json.dumps(obj,ensure_ascii=True,separators=(",",":"))+"\n")


def path_in(s,cwd):
    if not isinstance(s,str) or not s or s.startswith("~") or "\x00" in s or "$" in s:
        return None
    cwd=cwd if isinstance(cwd,str) else ""
    parts=[x for x in cwd.split("/") if re.fullmatch(r"swebench[_-][\w.-]+",x,re.I)]
    root=parts[0] if parts else None
    p=posixpath.normpath(s)
    if root:
        if p.split("/")[0]==root:
            p="/@trace/"+p
        elif p.startswith("/") and root in p.split("/"):
            p="/@trace/"+p[p.index("/"+root+"/")+1:] if "/"+root+"/" in p else "/@trace/"+root
        if root in cwd.split("/"):
            cwd="/@trace/"+"/".join(cwd.split("/")[cwd.split("/").index(root):])
    if not p.startswith("/"):
        if not cwd:
            return None
        p=posixpath.join(cwd if cwd.startswith("/") else "/@trace/"+cwd,p)
    return posixpath.normpath(p)


def read_key(inp,cwd):
    if not isinstance(inp,dict) or not set(inp)<= {"file_path","offset","limit"}:
        return None
    p=path_in(inp.get("file_path"),cwd)
    if not p or any(type(inp[k]) is not int or inp[k]<0 for k in ("offset","limit") if k in inp):
        return None
    return p,inp.get("offset"),inp.get("limit")


def turns(raw):
    calls=[];results={};mid=None;reset=False;last_uuid=None;last_session=None
    for line in raw.splitlines():
        if not line.strip():
            continue
        r=json.loads(line)
        if r.get("type") not in ("assistant","user") or r.get("isSidechain"):
            continue
        u=r.get("uuid");parent=r.get("parentUuid");sess=r.get("sessionId")
        discontinuity=bool(last_uuid and u and (parent!=last_uuid or sess!=last_session))
        m=r.get("message") or {}
        current=m.get("id") or u
        if discontinuity:
            if mid is not None:
                yield calls,results,reset
            calls=[];results={};mid=None;reset=True
        if r["type"]=="assistant" and current!=mid and mid is not None:
            yield calls,results,reset
            calls=[];results={};mid=None;reset=False
        if r["type"]=="assistant":
            mid=current
        content=m.get("content")
        if isinstance(content,list):
            for v in content:
                if not isinstance(v,dict):
                    continue
                if r["type"]=="assistant" and v.get("type")=="tool_use":
                    args=v.get("input")
                    calls.append((v.get("name"),args if isinstance(args,dict) else {},v.get("id"),r.get("cwd")))
                if r["type"]=="user" and v.get("type")=="tool_result" and mid is not None:
                    tid=v.get("tool_use_id")
                    results[tid]=None if tid in results else (v,r.get("toolUseResult"))
        if u:
            last_uuid,last_session=u,sess
    if mid is not None:
        yield calls,results,reset


def visible(result):
    if not result:
        return "unknown",None
    payload=result[0]
    body=payload.get("content")
    if payload.get("is_error") or isinstance(body,str) and body.startswith("<tool_use_error>"):
        return "error",body
    if not isinstance(body,str):
        return "unknown",None
    return "success",body


def numbered(raw,sep):
    return "\n".join(f"{i:6d}"+sep+line for i,line in enumerate(raw.split("\n"),1))


def reconstruct(result,body):
    ex=result[1] if result else None
    if not isinstance(ex,dict) or ex.get("type")!="text" or not isinstance(ex.get("file"),dict):
        return None
    f=ex["file"];raw=f.get("content")
    if not isinstance(raw,str) or f.get("startLine")!=1 or f.get("numLines")!=f.get("totalLines") or len(raw.split("\n"))!=f.get("totalLines"):
        return None
    for sep in ("\u2192","\t"):
        text=numbered(raw,sep)
        if not body.startswith(text):
            continue
        tail=body[len(text):]
        if tail in ("","\n","\n\n") or (tail.count("<system-reminder>")==1 and tail.count("</system-reminder>")==1 and
                re.fullmatch(r"\n*<system-reminder>.*?</system-reminder>\n*",tail,re.S)):
            return raw,sep,tail
    return None


@dataclass
class Entry:
    text: str
    full: tuple|None
    fill: int
    slot: int
    size: int
    edits: tuple


class Cache:
    def __init__(self,name):
        self.name=name;self.items=OrderedDict();self.bytes=0;self.peak=0;self.stats=Counter()

    def remove(self,key):
        self.bytes-=self.items.pop(key).size

    def insert(self,key,body,full,b,slot,edits=()):
        if len(body.encode())>16_384:
            return False
        if key in self.items:
            self.remove(key)
        size=len(json.dumps(key,ensure_ascii=False).encode())+len(body.encode())
        size+=sum(len(x.encode()) for x in full) if full else 0
        self.items[key]=Entry(body,full,b,slot,size,edits)
        self.bytes+=size
        while len(self.items)>32 or self.bytes>262_144:
            self.remove(next(iter(self.items)))
            self.stats["capacity_evictions"]+=1
        self.peak=max(self.peak,self.bytes)
        return key in self.items

    def invalidate(self,b,reset,global_unknown,writes):
        if reset or (self.name in ("selective","write_through","flush") and global_unknown) or (self.name=="flush" and writes):
            self.stats["invalidate_global"]+=len(self.items)
            self.items.clear();self.bytes=0
        elif self.name in ("selective","write_through"):
            for k in list(self.items):
                if any(k[0]==p or k[0].startswith(p+"/") or p.startswith(k[0]+"/") for p in writes):
                    self.remove(k);self.stats["invalidate_path"]+=1
        elif self.name.startswith("ttl"):
            for k,v in list(self.items.items()):
                if b-v.fill>int(self.name[3:]):
                    self.remove(k)


def simulate(raw,sid,queryfile,batchfile):
    caches=[Cache(n) for n in ARMS]
    counts=Counter();seen=set();repo=None
    for b,(calls,results,reset) in enumerate(turns(raw)):
        counts["batches"]+=1
        counts["branch_resets"]+=int(reset)
        if reset:
            seen.clear()
        writes=set();unknown=False
        parsed=[]
        for name,inp,tid,cwd in calls:
            counts["tools"]+=1
            if name=="Bash" and not repo:
                urls=CLONE.findall(str(inp.get("command","")))
                if len(set(urls))==1:
                    repo=urls[0].lower().removesuffix(".git")
            key=read_key(inp,cwd) if name=="Read" else None
            if name in MUTATE:
                p=path_in(inp.get("file_path"),cwd)
                if p:
                    writes.add(p)
                else:
                    unknown=True
            elif name not in READONLY:
                unknown=True
            if name=="Read":
                counts["reads"]+=1
                counts["path_or_args_unresolved"]+=int(not key)
            parsed.append((name,inp,tid,key,cwd))
        # Snapshot the sole Edit candidate before invalidating; its result may be
        # used for a deterministic update but cannot supply unobserved file text.
        edit=None
        wc=caches[-1]
        if not reset and len(parsed)==1 and parsed[0][0]=="Edit" and len(writes)==1:
            edit_key=(next(iter(writes)),None,None)
            old=wc.items.get(edit_key)
            edit=(edit_key,old,parsed[0][1],parsed[0][2])
        for c in caches:
            c.invalidate(b,reset,unknown,writes)
        pending=[]
        for slot,(name,inp,tid,key,cwd) in enumerate(parsed):
            if key and not unknown and not writes:
                pending.append((slot,tid,key,[c.items.get(key) for c in caches],key in seen))
            elif key:
                counts["mixed_suppressed"]+=1
        seen.update(q[2] for q in pending)
        for slot,tid,key,guesses,repeated in pending:
            result=results.get(tid)
            status,body=visible(result)
            counts["eligible"]+=1;counts["actual_"+status]+=1;counts["repeated"]+=int(repeated)
            admitted=status=="success" and len(body.encode())<=16_384
            full=reconstruct(result,body) if admitted and key[1:]==(None,None) else None
            counts["admissible"]+=int(admitted);counts["roundtrip_full"]+=int(bool(full))
            delivered=[]
            for c,old in zip(caches,guesses):
                if old:
                    assert old.fill<b
                    if key in c.items:c.items.move_to_end(key)
                    obs=("unknown" if status=="unknown" else "correct" if status=="success" and body==old.text else "stale")
                    c.stats[obs]+=1
                    if old.edits:c.stats["edited_"+obs]+=1
                    delivered.append([old.fill,old.slot,obs,list(old.edits),sha(old.text.encode())])
                else:
                    c.stats["miss"]+=1;delivered.append(None)
                    if admitted:c.insert(key,body,full,b,slot)
            emit(queryfile,{"sid":sid,"b":b,"slot":slot,"key":key,"repeated":repeated,
                            "actual":status,"sha256":sha(body.encode()) if isinstance(body,str) else None,
                            "admitted":admitted,"roundtrip_full":bool(full),"arms":delivered})
        edit_state=None
        if edit:
            key,entry,inp,tid=edit;old=inp.get("old_string");new=inp.get("new_string");all_=inp.get("replace_all",False)
            status,_=visible(results.get(tid))
            if status!="success":edit_state="unconfirmed"
            elif not entry:edit_state="no_default_entry"
            elif not entry.full:edit_state="unverified_full_text"
            elif not isinstance(old,str) or not old or not isinstance(new,str) or type(all_)!=bool:edit_state="unsupported_edit"
            else:
                src,sep,tail=entry.full
                count=src.count(old)
                if count==0 or (not all_ and count!=1):edit_state="ambiguous_or_missing"
                else:
                    updated=src.replace(old,new) if all_ else src.replace(old,new,1)
                    body=numbered(updated,sep)+tail
                    edits=entry.edits+(b,)
                    ok=wc.insert(key,body,(updated,sep,tail),entry.fill,entry.slot,edits)
                    edit_state="updated" if ok else "over_budget"
            counts["edit_"+edit_state]+=1
        for c in caches:c.stats["sum_end_bytes"]+=c.bytes
        emit(batchfile,{"sid":sid,"b":b,"reset":reset,"tools":[r[0] for r in parsed],
                        "unknown":unknown,"writes":sorted(writes),"edit":edit_state})
    return {"repo_proxy":repo,"counts":counts,"arms":{c.name:{**c.stats,"peak":c.peak} for c in caches}}


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--freeze",action="store_true")
    ap.add_argument("--data",type=Path,default=Path("D:/CodexResearch/x20-swe-context"))
    args=ap.parse_args()
    sig={n:sha((HERE/n).read_bytes()) for n in ("sources.json","protocol.md","replay.py","analyze.py")}
    frozen=HERE/"freeze.json"
    if args.freeze:
        with frozen.open("x",encoding="utf8") as f:json.dump({"utc":datetime.now(timezone.utc).isoformat(),"sha256":sig},f,indent=2)
        return
    assert json.loads(frozen.read_bytes())["sha256"]==sig
    sources=json.loads((HERE/"sources.json").read_bytes())["files"];assert len(sources)==300
    start=time.monotonic()
    with gzip.open(HERE/"queries.jsonl.gz","wt",encoding="utf8",compresslevel=5) as q, gzip.open(HERE/"batches.jsonl.gz","wt",encoding="utf8",compresslevel=5) as bs,gzip.open(HERE/"histories.jsonl.gz","wt",encoding="utf8",compresslevel=5) as h:
        for s in sources:
            raw=(args.data/s["relative"]).read_bytes()
            assert sha(raw)==s["sha256"]
            sid=Path(s["relative"]).stem
            emit(h,{"sid":sid,"sha256":s["sha256"],**simulate(raw,sid,q,bs)})
    (HERE/"runtime.json").write_text(json.dumps({"seconds":time.monotonic()-start,"python":sys.version,"arms":ARMS}),encoding="utf8")


if __name__=="__main__":
    main()

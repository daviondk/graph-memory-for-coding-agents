"""Run immutable-response read caches, without executing historical shell commands."""
import argparse
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
import platform
import re
import sys
import time
from pathlib import Path
from shell import classify

HERE=Path(__file__).resolve().parent
WITHIN=HERE.parent/"within_task"
ARMS=("unbounded","lru","ttl1","ttl3","ttl10","flush","selective")


def digest(b):
    return hashlib.sha256(b).hexdigest()


def dump(f,data):
    f.write(json.dumps(data,separators=(",",":"),ensure_ascii=True)+"\n")


def batches(messages):
    assistant=None
    following=[]
    for msg in messages:
        if msg["role"]=="assistant":
            if assistant is not None:
                yield assistant,following
            assistant,following=msg,[]
        elif assistant is not None and msg["role"]=="tool":
            following.append(msg)
    if assistant is not None:
        yield assistant,following


def declarations(assistant):
    raw=(assistant.get("extra") or {}).get("actions") or []
    if raw:
        return [(a.get("command",""),a.get("tool_call_id")) if isinstance(a,dict) else ("",None) for a in raw]
    out=[]
    for call in assistant.get("tool_calls") or []:
        args=(call.get("function") or {}).get("arguments")
        if isinstance(args,str):
            try:
                args=json.loads(args)
            except ValueError:
                args={}
        out.append((args.get("command","") if isinstance(args,dict) else "",call.get("id")))
    return out


@dataclass
class Observed:
    rc: int|None
    body: bytes|None
    clipped: bool
    writable: bool


def observation(msg):
    ex=msg.get("extra") or {}
    rc=ex.get("returncode")
    raw=ex.get("raw_output")
    content=msg.get("content")
    content=content if isinstance(content,str) else ""
    clipped="<output_head>" in content or "<output_tail>" in content or "<warning>" in content
    m=re.fullmatch(r"<returncode>(-?\d+)</returncode>\n<output>\n(.*)</output>",content,re.S)
    if type(rc) is not int and m:
        rc=int(m[1])
    if type(rc) is not int:
        rc=None
    if isinstance(raw,str):
        body=raw.encode()
    elif m and not clipped:
        body=m[2].encode()
    else:
        body=None
    intact=bool(m and not clipped and rc==int(m[1]) and body==m[2].encode())
    return Observed(rc,body,clipped,intact and len(body)<=16_384)


@dataclass
class Entry:
    path: str
    fill: int
    slot: int
    rc: int
    body: bytes
    size: int


class Cache:
    def __init__(self,name):
        self.name=name
        self.items=OrderedDict()
        self.bytes=0
        self.peak=0
        self.count=Counter()

    def discard(self,reason,keys):
        keys=list(keys)
        for k in keys:
            self.bytes-=self.items.pop(k).size
        self.count["evict_"+reason]+=len(keys)
        return len(keys)

    def expire(self,b,writes,unknown):
        if self.name.startswith("ttl"):
            ttl=int(self.name[3:])
            return self.discard("ttl",(k for k,v in self.items.items() if b-v.fill>ttl))
        if self.name=="flush" and (writes or unknown) or self.name=="selective" and unknown:
            return self.discard("global",self.items)
        if self.name=="selective" and writes:
            def related(v):
                return any(v==p or v.startswith(p+"/") or p.startswith(v+"/") for p in writes)
            return self.discard("path",(k for k,v in self.items.items() if related(v.path)))
        return 0

    def store(self,cmd,path,b,slot,obs):
        if not obs.writable:
            self.count["fill_rejected"]+=1
            return
        if cmd in self.items:
            self.discard("same_batch_overwrite",[cmd])
        size=len(cmd.encode())+len(path.encode())+len(str(obs.rc).encode())+len(obs.body)
        self.items[cmd]=Entry(path,b,slot,obs.rc,obs.body,size)
        self.bytes+=size
        self.count["writes"]+=1
        self.count["written_bytes"]+=size
        if self.name!="unbounded":
            while len(self.items)>32 or self.bytes>262_144:
                self.discard("capacity",[next(iter(self.items))])
        self.peak=max(self.peak,self.bytes)


def simulate(messages,sid,queries,batchlog):
    caches=[Cache(name) for name in ARMS]
    counts=Counter()
    seen=set()
    for b,(assistant,tools) in enumerate(batches(messages)):
        declared=declarations(assistant)
        types=[classify(cmd) for cmd,_ in declared]
        unknown=any(t.mode=="global" for t in types)
        writes=set(p for t in types if t.mode=="write" for p in t.paths)
        mixed=unknown or bool(writes)
        counts["batches"]+=1
        counts["commands"]+=len(types)
        counts["unknown_batches"]+=int(unknown)
        counts["known_write_batches"]+=int(bool(writes))
        counts["mixed_suppressed_queries"]+=sum(t.mode=="query" for t in types) if mixed else 0
        counts.update("cmd_"+t.mode for t in types)
        invalid=[c.expire(b,writes,unknown) for c in caches]
        # All choices are made from this prior snapshot. Actual tool outputs stay
        # outside the policy and are accessed only after the last decision here.
        pending=[]
        for slot,((cmd,_),t) in enumerate(zip(declared,types)):
            if t.mode=="query" and not mixed:
                chosen=[c.items.get(cmd) for c in caches]
                pending.append((slot,cmd,t.paths[0],chosen,cmd in seen))
        seen.update(x[1] for x in pending)
        lookup={}
        ambiguous=set()
        for msg in tools:
            tid=msg.get("tool_call_id")
            if tid in lookup:
                ambiguous.add(tid)
            lookup[tid]=msg
        for slot,cmd,path,chosen,repeated in pending:
            tid=declared[slot][1]
            obs=observation(lookup.get(tid,{}) if tid and tid not in ambiguous else {})
            counts["eligible"]+=1
            counts["repeated_eligible_key"]+=int(repeated)
            counts["observed_truncated"]+=int(obs.clipped)
            counts["recordable"]+=int(obs.writable)
            counts["oversize"]+=int(obs.body is not None and len(obs.body)>16384)
            counts["unscorable_actual"]+=int(obs.body is None or obs.rc is None)
            result=[]
            for c,ent in zip(caches,chosen):
                if ent is None:
                    c.count["miss"]+=1
                    result.append(None)
                    c.store(cmd,path,b,slot,obs)
                else:
                    assert ent.fill < b and ent.path==path
                    if cmd in c.items:
                        c.items.move_to_end(cmd)
                    code=("unknown" if obs.rc is None or obs.body is None else
                          "correct" if (obs.rc,obs.body)==(ent.rc,ent.body) else "stale")
                    c.count[code]+=1
                    c.count["delivered_bytes"]+=len(ent.body)
                    result.append([ent.fill,ent.slot,code])
            dump(queries,{"sid":sid,"b":b,"slot":slot,"cmd_sha256":digest(cmd.encode()),"path":path,
                "repeated":repeated,"rc":obs.rc,"bytes":None if obs.body is None else len(obs.body),
                "stdout_sha256":None if obs.body is None else digest(obs.body),"clipped":obs.clipped,
                "writable":obs.writable,"arms":result})
        for c in caches:
            c.count["sum_batch_end_bytes"]+=c.bytes
        dump(batchlog,{"sid":sid,"b":b,"types":[t.mode for t in types],"write_paths":sorted(writes),
            "evicted_before":invalid,"sizes":[c.bytes for c in caches]})
    return {"counts":dict(counts),"arms":{c.name:{**c.count,"peak":c.peak} for c in caches}}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--base",type=Path,default=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench"))
    ap.add_argument("--freeze",action="store_true")
    args=ap.parse_args()
    files=("protocol.md","shell.py","run.py","summary.py")
    signature={name:digest((HERE/name).read_bytes()) for name in files}
    freeze=HERE/"freeze.json"
    if args.freeze:
        with freeze.open("x",encoding="utf8") as f:
            json.dump({"utc":datetime.now(timezone.utc).isoformat(),"sha256":signature},f,indent=2)
        return
    assert json.loads(freeze.read_bytes())["sha256"]==signature
    start=time.monotonic()
    with gzip.open(WITHIN/"histories.jsonl.gz","rt",encoding="utf8") as f:
        roster=list(map(json.loads,f))
    assert len(roster)==2470 and len(set(h["path"] for h in roster))==2470
    with gzip.open(HERE/"queries.jsonl.gz","wt",encoding="utf8",compresslevel=5) as queries, \
         gzip.open(HERE/"batches.jsonl.gz","wt",encoding="utf8",compresslevel=5) as batches_file, \
         gzip.open(HERE/"histories.jsonl.gz","wt",encoding="utf8",compresslevel=5) as histories:
        for i,h in enumerate(roster,1):
            _,_,repo,sid,_=h["path"].split("/")
            raw=(args.base/"benchmark"/h["path"]).read_bytes()
            assert digest(raw)==h["sha256"]
            data=json.loads(raw)
            messages=data if isinstance(data,list) else data["messages"]
            result=simulate(messages,sid,queries,batches_file)
            dump(histories,{"sid":sid,"repo":repo,"path":h["path"],"sha256":h["sha256"],**result})
            if i%500==0:
                print(f"{i}/{len(roster)} {time.monotonic()-start:.1f}s",flush=True)
    (HERE/"runtime.json").write_text(json.dumps({"python":sys.version,"platform":platform.platform(),
        "seconds":time.monotonic()-start,"arms":ARMS,"histories":len(roster)},indent=2),encoding="utf8")


if __name__=="__main__":
    main()

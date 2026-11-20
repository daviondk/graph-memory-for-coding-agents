"""Paired external edits and native read_file observations with exact reconstruction."""
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import random
from acquire import D, V, h, save
from mcp import Client, dumpgz
from workspace_tools import expected, stamp, target

CASES=("repeat","touch","neighbor","replace","replace_restore","atomic_restore","append","prepend")
RULES={"mtime_size":("mtime","size"),"mtime_size_id":("mtime","size","dev","ino"),"ntfs_change":("mtime","size","dev","ino","change")}
R=D/"scratch"
def lines(text):
    return [(int(m[1]),m[2]) for s in text.splitlines() if (m:=re.fullmatch(r"(\d+):[0-9a-f]{2}\|(.*)",s))]
def decode(reply,old):
    if reply.startswith("[unchanged since"):return old
    if not reply.startswith("[changed since"):
        return "".join(v+"\n" for i,v in lines(reply)).encode()
    orig=old.decode().splitlines()
    removed=set();added=[]
    for line in reply.splitlines():
        if line.startswith("-"):
            nums=re.match(r"^-(\d+):[0-9a-f]{2}(?:\D+?(\d+):[0-9a-f]{2})? \((\d+) lines?\)",line)
            assert nums,line
            i=int(nums[1])-1
            removed.update(range(i,i+int(nums[3])))
        if line.startswith("+"):
            m=re.fullmatch(r"\+(\d+):[0-9a-f]{2}\|(.*)",line)
            assert m,line
            added.append((int(m[1])-1,m[2]))
    final=[v for i,v in enumerate(orig) if i not in removed]
    for i,v in sorted(added):final.insert(i,v)
    return ("\n".join(final)+"\n").encode()
def marker(b):
    return f"[unchanged since you last viewed or edited it (compared with the file on disk just now): {len(b.splitlines())} lines. Pass full: true to re-read, or view a line range.]"
def actual_range(reply):
    return "".join(line+"\n" for _,line in lines(reply)).encode()
def range_numbers(path,lo,hi):
    # Read a measured prefix in 512-byte unbuffered chunks. Includes any chunk over-read.
    fetched=0;blocks=[]
    with path.open("rb",buffering=0) as f:
        nl=0
        while nl<hi:
            chunk=f.read(512)
            if not chunk:break
            blocks.append(chunk);fetched+=len(chunk);nl+=chunk.count(b"\n")
    return b"".join(b"".join(blocks).splitlines(keepends=True)[lo-1:hi]),fetched

def main():
    R.mkdir(exist_ok=True)
    locks=["PROTOCOL_RU.md","WINDOWS_VALIDATOR.md","window_amendment.md","fixtures.json","octofs_source.json","workspace_tools.py","mcp.py","experiment.py"]
    save("design.lock.json",{k:h((D/k).read_bytes()) for k in locks})
    assert h((V/"octofs.exe").read_bytes())==json.loads((D/"octofs_source.json").read_bytes())["exe_sha256"]
    sessions={m:Client(R,m) for m in ("native","full",*RULES)}
    noepoch=Client(R,"anonymous",None)
    context=R/"context.py";context.write_bytes(b"first=1\nsecond=2\n")
    for c in (noepoch,sessions["native"]):
        one,_=c.view(context.name);two,_=c.view(context.name)
        assert (two.startswith("[unchanged since"))==(c is sessions["native"])
    new_session=Client(R,"renewed",1)
    reset,_=new_session.view(context.name)
    assert reset==one
    save("context_control.json",{"no_epoch":noepoch.rows,"renewed_session":new_session.rows,"native":sessions["native"].rows[:3]})
    noepoch.close();new_session.close()
    fixtures=[v for r in json.loads((D/"fixtures.json").read_bytes()) for v in r["chosen"]]
    pairs=[(i,scenario) for i in range(len(fixtures)) for scenario in CASES]
    random.Random(5349).shuffle(pairs)
    receipts=[];metrics=[];stamps=[]
    def measure(case,scope,policy,first,actual,truth,fetched,display,elapsed,hit=False,**extra):
        metrics.append(dict(case=case,scope=scope,policy=policy,prior_bytes=len(first),truth_bytes=len(truth),
               changed=first!=truth,correct=actual==truth,actual_sha=h(actual),truth_sha=h(truth),cache_hit=hit,
               file_payload_bytes=fetched,response_text_bytes=display,elapsed_ns=elapsed,**extra))
    for turn,(i,scenario) in enumerate(pairs):
        item=fixtures[i];old=(D/item["fixture"]).read_bytes();assert h(old)==item["sha256"]
        path=R/f"case-{i:02}-{scenario}.py";path.write_bytes(old)
        pos=target(old)[0];lo=pos-3;hi=pos+4
        data=old.splitlines(keepends=True);oldrange=b"".join(data[lo-1:hi])
        offset=sum(map(len,data[:lo-1]))
        init={}
        for m,client in sessions.items():
            text,row=client.view(path.name);assert decode(text,b"")==old
            state=stamp(path,m=="ntfs_change") if m in RULES else None
            init[m]=state
            receipts.append({"fixture":i,"scenario":scenario,"policy":m,"phase":"original",**row})
        before=stamp(path,True)
        subprocess.run([sys.executable,"-B",str(D/"workspace_tools.py"),str(path),scenario],check=True)
        after=stamp(path,True);gold=expected(old,scenario)
        assert path.read_bytes()==gold
        targetrange=b"".join(gold.splitlines(keepends=True)[lo-1:hi])
        case=f"{i:02}/{scenario}"
        stamps.append(dict(case=case,fixture=item["fixture"],index=i,scenario=scenario,old_sha=h(old),new_sha=h(gold),
                           lo=lo,hi=hi,offset=offset,before=before,after=after,old_range_sha=h(oldrange),new_range_sha=h(targetrange)))
        order=list(sessions);random.Random(314+turn).shuffle(order)
        for m in order:
            clock=time.perf_counter_ns()
            hit=False;stat_calls=0;native_calls=0
            if m in RULES:
                current=stamp(path,m=="ntfs_change");stat_calls=1
                hit=all(current[k]==init[m][k] for k in RULES[m])
            if hit:
                reply=marker(old);fetched=0;wire_bytes=None
            else:
                reply,row=sessions[m].view(path.name,**({"full":True} if m=="full" else {}))
                receipts.append({"fixture":i,"scenario":scenario,"policy":m,"phase":"repeat",**row})
                native_calls=1;wire_bytes=row["response_bytes"];fetched=len(gold)
            elapsed=time.perf_counter_ns()-clock;decoded=decode(reply,old)
            measure(case,"whole",m,old,decoded,gold,fetched,len(reply.encode()),elapsed,hit,
                    receipt_bytes=wire_bytes,metadata_checks=stat_calls,native_calls=native_calls,shape="unchanged" if reply.startswith("[unchanged") else "delta" if reply.startswith("[changed") else "full")
        clock=time.perf_counter_ns();read=path.read_bytes();elapsed=time.perf_counter_ns()-clock
        measure(case,"whole","direct_reread",old,read,gold,len(read),len(read),elapsed)
        clock=time.perf_counter_ns();read=path.read_bytes();equal=old==read
        reply=marker(old).encode() if equal else read;elapsed=time.perf_counter_ns()-clock
        measure(case,"whole","byte_compare",old,old if equal else read,gold,len(read),len(reply),elapsed,equal)
        clock=time.perf_counter_ns();reply,row=sessions["native"].view(path.name,start=lo,end=hi);elapsed=time.perf_counter_ns()-clock
        receipts.append({"fixture":i,"scenario":scenario,"policy":"native_range","phase":"repeat",**row})
        measure(case,"range","native_range",oldrange,actual_range(reply),targetrange,len(gold),len(reply.encode()),elapsed,receipt_bytes=row["response_bytes"])
        clock=time.perf_counter_ns();ans,n=range_numbers(path,lo,hi);elapsed=time.perf_counter_ns()-clock
        measure(case,"range","line_numbers",oldrange,ans,targetrange,n,len(ans),elapsed)
        clock=time.perf_counter_ns()
        with path.open("rb",buffering=0) as stream:
            stream.seek(offset);ans=stream.read(len(oldrange))
        elapsed=time.perf_counter_ns()-clock
        measure(case,"range","cached_byte_offset",oldrange,ans,targetrange,len(ans),len(ans),elapsed)
    for client in sessions.values():client.close()
    dumpgz(D/"native_calls.json.gz",receipts)
    dumpgz(D/"paired_metrics.json.gz",metrics)
    save("pair_states.json",stamps)
    save("runtime.json",{"python":platform.python_version(),"os":platform.platform(),"events":len(pairs),"fixtures":len(fixtures),
                         "scope":"one NTFS fixed volume, sequential external writer; no concurrent query-time race",
                         "file_payload_bytes":"Python controls physically issue recorded bytes or one whole read. Native view counted one input length lower bound from published io_read_capped; no hardware I/O instrumentation.",
                         "response_text_bytes":"UTF-8 tool text; raw MCP wrapper bytes separately in native_calls. Python direct protocols return source bytes; native renders line IDs."})
    print(len(receipts),len(metrics),len(stamps))
if __name__=="__main__":main()

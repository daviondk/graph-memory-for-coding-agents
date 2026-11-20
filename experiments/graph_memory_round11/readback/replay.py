"""Lossless observations with bounded, directly visible evidence references."""
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import gzip, json, random, sys, time
from tokenizers import Tokenizer
from prepare import ROOT, WORK, sha, write
TOKENIZER=WORK/"memory_session5/live/tokenizer.json"
tok=Tokenizer.from_file(str(TOKENIZER))
@lru_cache(maxsize=16000)
def tokens(s):return len(tok.encode(s,add_special_tokens=False).ids)
def literal(n,s):return f"{n}\t{s}\n"
def ref(turn,start,count):return f"@{turn} {start} {count}\n"
def packet(turn,wire):return f"[view {turn}]\n"+wire
def match_wire(lines,bases):
    chunks=[];pos=0
    while pos<len(lines):
        start=lines[pos][0]
        options=[]
        for event,lookup in bases:
            k=pos
            while k<len(lines):
                n,s=lines[k]
                if n!=start+(k-pos) or lookup.get(n)!=s:break
                k+=1
            if k>pos:options.append((k,event))
        end,event=max(options,default=(pos,-1))
        raw="".join(literal(n,s) for n,s in lines[pos:end])
        marker=ref(event,start,end-pos)
        if end>pos and tokens(marker)<tokens(raw):
            chunks.append(marker);pos=end
        else:
            chunks.append(literal(*lines[pos]));pos+=1
    return "".join(chunks)
def decode(wire,bases):
    lookups=dict(bases);decoded=[];visible={}; refs=[]
    for line in wire.split("\n")[:-1]:
        if line.startswith("@"):
            event,start,size=map(int,line[1:].split())
            refs.append(event)
            for n in range(start,start+size):decoded.append([n,lookups[event][n]])
        else:
            ns,s=line.split("\t",1);n=int(ns);visible[n]=s;decoded.append([n,s])
    return decoded,visible,refs
def session(views,window,mode,method):
    old={};result=[]
    for v in views:
        turn,path,lines=v["turn"],v["path"],v["lines"]
        old={k:x for k,x in old.items() if turn-k<=window}
        bases=[(k,x) for k,(name,x) in old.items() if name==path and x]
        raw="".join(literal(n,s) for n,s in lines);candidates=[raw]
        if method=="whole":
            nums=[n for n,s in lines]
            if nums==list(range(nums[0],nums[0]+len(nums))):
                for e,lookup in bases:
                    if all(lookup.get(n)==s for n,s in lines):candidates.append(ref(e,nums[0],len(lines)))
        if method in ("single","union"):
            candidates.extend(match_wire(lines,[base]) for base in bases)
            if method=="union" and len(bases)>1:candidates.append(match_wire(lines,bases))
        best=min(candidates,key=lambda s:tokens(packet(turn,s)))
        decoded,visible,refs=decode(best,bases)
        assert decoded==lines
        old[turn]=(path,dict(lines) if mode=="runtime" else visible)
        result.append(dict(turn=turn,raw=tokens(packet(turn,raw)),tokens=tokens(packet(turn,best)),
            bytes=len(packet(turn,best).encode()),digest=sha(raw.encode()),references=refs,
            # Every referenced packet is reproducible from the inputs and recorded wire.
            wire=best if refs else None))
    return result
def main():
    obj=json.loads(gzip.decompress((ROOT/"views.gz").read_bytes()))
    locked=json.loads((ROOT/"input-lock.json").read_bytes())["files"]
    assert all(sha((ROOT/n).read_bytes())==h for n,h in locked.items())
    start=time.monotonic();raw=[];long={};panelrows=defaultdict(list)
    for task,record in sorted(obj.items()):
        for w in (4,8,16):
            for mode in ("visible","runtime"):
                rr={m:session(record["views"],w,mode,m) for m in ("raw","whole","single","union")}
                panelrows[record["panel"],w,mode].append({m:sum(x["tokens"] for x in rows) for m,rows in rr.items()})
                for m,rows in rr.items():
                    compressed=[x for x in rows if x["references"]]
                    raw.append(dict(task=task,panel=record["panel"],mode=mode,method=m,window=w,
                        messages=len(rows),tokens=sum(x["tokens"] for x in rows),compressed=len(compressed),
                        mixed=sum(len(set(x["references"]))>1 for x in rows)))
                    if w==8 and mode=="visible" and m!="raw":long[task+"|"+m]=compressed
    write("rows.gz",raw);write("wires-primary.gz",long)
    results={}
    for (panel,w,mode),rows in sorted(panelrows.items()):
        sums={m:sum(x[m] for x in rows) for m in ("raw","whole","single","union")}
        diffs=[x["single"]-x["union"] for x in rows]
        rng=random.Random(17631);boot=[]
        if w==8 and mode=="visible":
            for _ in range(5000):
                sample=rng.choices(rows,k=len(rows))
                total=sum(i["raw"] for i in sample)
                if total:boot.append(100*sum(i["single"]-i["union"] for i in sample)/total)
            boot.sort()
        results[f"{panel}|{w}|{mode}"]=dict(totals=sums,n=len(rows),wins=sum(x>0 for x in diffs),losses=sum(x<0 for x in diffs),saved=sum(diffs),
            points=100*sum(diffs)/sums["raw"] if sums["raw"] else None,
            ci=[boot[int(p*(len(boot)-1))] for p in (.025,.975)] if boot else None)
    write("results.json",results)
    write("receipt.json",dict(tasks=len(obj),views=sum(len(x["views"]) for x in obj.values()),events=sum(x["events"] for x in obj.values()),
        unique_replays=sum(x["messages"] for x in raw),elapsed=time.monotonic()-start,
        tokenizer_file=str(TOKENIZER),tokenizer_sha=sha(TOKENIZER.read_bytes()),
        files={n:sha((ROOT/n).read_bytes()) for n in ("replay.py","input-lock.json","rows.gz","wires-primary.gz","results.json")}))
if __name__=="__main__":main()

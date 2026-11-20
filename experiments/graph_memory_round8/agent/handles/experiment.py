"""Follow-up on identical issues and actual same initial search, with a single compaction checkpoint."""
import json
import shutil
import sys
from pathlib import Path
CUR=Path(__file__).resolve().parent
PRIMARY=CUR.parent
sys.path.insert(0,str(PRIMARY))
import harness as h
import evaluate as e
from harness import call, obj, search, view, issuehead, read, write, FIX
D=CUR
h.D=CUR
h.ENDPOINT="http://127.0.0.1:18930/v1/chat/completions"
e.D=CUR
AGENT=h.AGENT+" A retained H1 address may or may not resolve. If it is unavailable, recover it by searching again or open an explicit file and line. Numbered hits returned by a new search are available."

def freeze():
    assert not (CUR/"input_lock.json").exists()
    original=h.read(PRIMARY/"input_lock.json"); ids=original["ids"]
    assert len(ids)==10
    fixed=["PROTOCOL_RU.md","experiment.py","start_server.ps1","../harness.py","../evaluate.py","../input_lock.json","../answer_lock.json","../compression/answer_lock.json","../compression/results.json","../../../graph_memory_round6/repair/transfer/grade.py"]
    for i in ids:
        dest=CUR/"tasks"/i;src=PRIMARY/"tasks"/i;dest.mkdir(parents=True,exist_ok=True)
        for name in ["public_input.json.gz","packets.json.gz"]:
            shutil.copyfile(src/name,dest/name);fixed.append((dest/name).relative_to(CUR).as_posix())
        shared=read(src/"flat.json.gz")["shared"]
        p=dest/"initial_observation.json.gz";write(p,shared);fixed.append(p.relative_to(CUR).as_posix())
        name=shared["key"]+".json.gz";p=CUR/"calls"/name;p.parent.mkdir(exist_ok=True)
        shutil.copyfile(PRIMARY/"calls"/name,p);fixed.append(p.relative_to(CUR).as_posix())
    write(CUR/"input_lock.json",{"ids":ids,"files":{k:h.filehash(CUR/k) for k in fixed}})

def compact(shared,alias):
    found=shared["history"]
    query=json.dumps(shared["query"],ensure_ascii=False)
    heading=f"Previous literal search {query}. Retained search summary. Earlier numbered IDs are compacted. Observed matches: {len(found)}."
    if not found:return heading+" No handle is present."
    hit=found[0]; lead=f"H{hit['id']} {hit['path']}:{hit['line']}: "
    first_line=shared["entry"].splitlines()[1]
    assert first_line.startswith(lead),lead
    excerpt=first_line[len(lead):][:120]
    def note(address):
        return f"First match file: {hit['path']}\nLine saved in memory: {address}\nSource excerpt: "+excerpt
    def size(text):return len(h.tok().encode(text,add_special_tokens=False).ids)
    while excerpt and max(size(note("unavailable")),size(note(str(hit["line"]))))>100:excerpt=excerpt[:-1]
    annotation=note("unavailable")
    assert size(annotation)<=100
    return heading+"\n"+annotation+"\nRetained handle: H1. Its address may be available or expired."

def infer():
    ids=h.check();assign={}
    for i in ids:
        cfg=read(CUR/"tasks"/i/"public_input.json.gz")
        assert all(h.filehash(CUR/"tasks"/i/"base"/p)==s for p,s in cfg["files"].items())
        raw=read(CUR/"tasks"/i/"initial_observation.json.gz");assign[i]={}
        for alias in sorted(h.METHODS,key=lambda a:h.sh((i+a+"|r8handles").encode())):
            shared={**raw,"entry":compact(raw,alias)}
            assign[i][alias]=do(i,alias,shared)
            print(i,alias,"done",flush=True)
    write(CUR/"assign.json",assign)
    paths=list((CUR/"calls").glob("*.json.gz"))+[CUR/"assign.json"]+[CUR/"tasks"/i/(m+".json.gz") for i in ids for m in h.METHODS]
    write(CUR/"answer_lock.json",{"input":h.filehash(CUR/"input_lock.json"),"files":{p.relative_to(CUR).as_posix():h.filehash(p) for p in paths}})

def inherited_cost():
    ids=e.answers();keys={read(CUR/"tasks"/i/"initial_observation.json.gz")["key"] for i in ids}
    allkeys={p.name.split(".")[0] for p in (CUR/"calls").glob("*.json.gz")}
    write(CUR/"physical_cost.json",{"reused_from_original":e.cost(sorted(keys)),"new_in_followup":e.cost(sorted(allkeys-keys))})

def main():
    stage=sys.argv[1]
    if stage=="freeze":freeze()
    elif stage=="extract":
        with h.concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(h.extract,h.check()))
    elif stage=="infer":infer()
    elif stage=="grade":e.grade()
    elif stage=="report":e.report();inherited_cost()
    elif stage=="verify":e.verify()
    elif stage=="export":
        import export_predictions as exporter
        exporter.main()

import re
def do(i,alias,shared):
    cfg=read(D/"tasks"/i/"public_input.json.gz");work=D/"tasks"/i/"base";paths=cfg["paths"]
    ptr=shared["ptr"];history=[dict(ptr) if alias=="evidence" else {}] if ptr else [];entries=[shared["entry"]]
    log=[];keys=[shared["key"]];tool_s=shared["tool_s"]
    for step in range(2):
        prompt=issuehead(cfg)+"\n\nTool observations:\n"+"\n\n".join(entries)+f"\n\nTool actions left: {2-step}."
        k,text=call(i,f"action{step}",AGENT,prompt,100);keys.append(k);a=obj(text)
        event={"decision":a,"ptr_before":ptr,"step":step,"key":k}
        if a.get("done") is True:
            event.update(type="done",tool_s=0);log.append(event);break
        if "search" in a:
            entry,ptr,seconds=search(work,paths,a["search"],history)
            event.update(type="search",tool_s=seconds)
        elif "read_hit" in a or "read" in a:
            selected=a.get("read",{});v=a.get("read_hit")
            if isinstance(v,str) and re.fullmatch(r"H?\d+",v):v=int(v.lstrip("H"))
            if "read_hit" in a:
                selected=history[v-1] if type(v)==int and 1<=v<=len(history) else {}
            if not isinstance(selected,dict):selected={}
            path,line=selected.get("path"),selected.get("line")
            entry,span,seconds=view(work,paths,path,line)
            event.update(type="read",span=span,matched=bool(ptr and (path,line)==(ptr["path"],ptr["line"])),tool_s=seconds)
            ptr=None
        else:
            entry="Unrecognized tool action";seconds=0;event.update(type="invalid",tool_s=0)
        entries.append(entry);log.append(event);tool_s+=seconds
    final=issuehead(cfg)+"\n\nActual tool observations:\n"+"\n\n".join(entries)
    k,unused=call(i,"fix",FIX,final,850);keys.append(k)
    out=dict(id=i,alias=alias,keys=keys,shared=shared,events=log,history=history,entries=entries,final=k,tool_seconds=tool_s)
    write(D/"tasks"/i/(alias+".json.gz"),out)
    return k

if __name__=="__main__":main()

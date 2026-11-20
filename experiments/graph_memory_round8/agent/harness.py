"""Prepare immutable source inputs and run the paired interactive reader. No grading data is read during inference."""
import collections, concurrent.futures, gzip, hashlib, importlib.util, json, math, os, re, shutil, subprocess, sys, tarfile, time, urllib.error, urllib.request
from pathlib import Path
from functools import lru_cache

D=Path(__file__).resolve().parent
WORK=D.parents[1]
R6=WORK/"graph_memory_round6/repair"
OLD=R6/"transfer"
R7=WORK/"graph_memory_round7/reader"
CODEC=WORK/"memory_session5/live/tokenizer.json"
ENDPOINT="http://127.0.0.1:18928/v1/chat/completions"
METHODS={"flat":"history","evidence":"pointer"}
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
def sh(b):return hashlib.sha256(b).hexdigest()
def filehash(p):return sh(p.read_bytes())
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    b=canonical(x) if p.suffix==".gz" else (json.dumps(x,ensure_ascii=False,indent=2)+"\n").encode()
    if p.suffix==".gz":b=gzip.compress(b,mtime=0)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(b);tmp.replace(p)
@lru_cache(maxsize=1)
def tok():
    from tokenizers import Tokenizer
    return Tokenizer.from_file(str(CODEC))
def shorten(s,n):
    encoded=tok().encode(s,add_special_tokens=False).ids
    return s if len(encoded)<=n else tok().decode(encoded[:n])
def freeze():
    assert not (D/"input_lock.json").exists()
    ids=read(OLD/"cohort.json")["ids"][20:30]
    assert len(ids)==len(set(ids))==10
    assert set(ids).isdisjoint(read(R7/"assign.json")) and set(ids).isdisjoint(read(OLD/"assign.json"))
    fixed=["PROTOCOL_RU.md","harness.py","evaluate.py","start_server.ps1","../../graph_memory_round6/repair/transfer/grade.py","../../graph_memory_round6/repair/transfer/cohort.json","../../graph_memory_round6/repair/model_receipt.json","../../graph_memory_round6/repair/runtime_receipt.json"]
    for i in ids:
        src=OLD/"tasks"/i;p=read(src/"public.json");packet=read(src/"packets.json.gz")
        paths=packet["paths"]
        assert p["repo"]=="sympy/sympy" and all(k.startswith("sympy/") and k.endswith(".py") and ".." not in k.split("/") and "tests" not in k.split("/") for k in paths)
        data={"id":i,"issue":shorten(p["problem_statement"],650),"paths":paths,"base":p["base_commit"],"checkout":read(src/"ready.json"),"files":{k:filehash(src/"base"/k) for k in paths}}
        f=D/"tasks"/i/"public_input.json.gz"; write(f,data);fixed.append(f.relative_to(D).as_posix())
        g=D/"tasks"/i/"packets.json.gz";write(g,{"paths":paths});fixed.append(g.relative_to(D).as_posix())
    write(D/"input_lock.json",{"ids":ids,"files":{n:filehash(D/n) for n in fixed},"tokenizer_sha256":filehash(CODEC),"rg_version":subprocess.check_output(["rg","--version"],text=True).splitlines()[0]})
def check():
    lock=read(D/"input_lock.json")
    assert all(filehash(D/k)==v for k,v in lock["files"].items())
    return lock["ids"]
def extract(i):
    cfg=read(D/"tasks"/i/"public_input.json.gz");a=OLD/"tasks"/i/"checkout.tar.gz"
    assert filehash(a)==cfg["checkout"]["sha256"]
    work=D/"tasks"/i/"base";work.mkdir(parents=True,exist_ok=True)
    with tarfile.open(a) as z:
        for m in z:
            rel=m.name.partition("/")[2]
            if not rel or not m.isfile():continue
            f=(work/rel).resolve();assert f.is_relative_to(work.resolve())
            f.parent.mkdir(parents=True,exist_ok=True)
            with z.extractfile(m) as src,f.open("wb") as dst:shutil.copyfileobj(src,dst)
    assert all(filehash(work/k)==v for k,v in cfg["files"].items())
def call(i,stage,system,prompt,cap):
    req=dict(model="qwen38-27b-ud-q4km",messages=[dict(role="system",content=system),dict(role="user",content=prompt)],temperature=0,seed=int(sh((i+"|"+stage).encode())[:7],16),max_tokens=cap,repeat_penalty=1,cache_prompt=False,stream=False,chat_template_kwargs={"enable_thinking":False})
    key=sh(canonical(req));p=D/"calls"/(key+".json.gz")
    if not p.exists():
        attempts=[]
        for trial in range(3):
            start=time.monotonic()
            try:
                msg=urllib.request.Request(ENDPOINT,data=canonical(req),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(msg,timeout=240) as r:ans=json.load(r)
                attempts.append({"elapsed":time.monotonic()-start,"success":True})
                break
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"HTTP {e.code}: "+e.read(220).decode(errors="replace")) from e
            except OSError as e:
                attempts.append({"elapsed":time.monotonic()-start,"error":type(e).__name__})
                if trial==2:raise
                time.sleep(2)
        assert isinstance(ans["choices"][0]["message"]["content"],str)
        write(p,dict(request=req,response=ans,attempts=attempts))
    stored=read(p);assert stored["request"]==req
    text=stored["response"]["choices"][0]["message"]["content"]
    return key,text
def obj(text):
    s=text.strip()
    if s.startswith(chr(96)*3):s=re.sub(r"^\x60{3}(?:json)?|\x60{3}$","",s,flags=re.I).strip()
    try:
        result=json.loads(s)
        return result if isinstance(result,dict) else {}
    except ValueError:return {}
def issuehead(cfg):
    return "Issue:\n"+cfg["issue"]+"\n\nAvailable historical source files:\n"+"\n".join(cfg["paths"])
SEARCH='Choose one short, exact literal search string for this issue. The tool searches the listed Python source files case-insensitively. Prefer the discriminating identifier or code fragment likely to identify the implementation. Output a JSON object {"search":"literal"}.'
AGENT=('You are inspecting a historical mathematics library before editing. Choose ONE tool action in JSON. '
       'Use {"read_hit":ID} to open around any numbered search match from history, '
       '{"read":{"path":"listed/file.py","line":NUMBER}} to open any listed location, '
       '{"search":"short exact literal"} to search again, or {"done":true} if sufficient. '
       'Prefer opening the most relevant implementation before proposing a fix. IDs and line numbers are 1-based.')
FIX=('Repair the mathematical library using the issue and observations below. Output only JSON with an edits array. '
     'Each item has path (as listed), old (one exact unique contiguous substring in the unmodified file) and new '
     '(replacement). Preserve literal indentation. Use minimal edits. Line numbers and search-result IDs are not part of the file.')
def search(work,paths,query,history):
    t=time.monotonic();found={}
    if isinstance(query,str) and 1<=len(query)<=96 and not any(c in query for c in "\n\r\0"):
        argv=["rg","--no-config","--no-heading","--with-filename","--color","never","--max-count","8","--line-number","--ignore-case","--fixed-strings","--",query,*paths]
        proc=subprocess.run(argv,cwd=work,capture_output=True,timeout=15)
        if proc.returncode not in (0,1):raise RuntimeError(proc.stderr.decode(errors="replace")[:200])
        for ln in proc.stdout.decode("utf8",errors="replace").splitlines():
            path,sep,rest=ln.replace("\\","/",1).partition(":")
            number,sep2,line=rest.partition(":")
            path=path.replace("\\","/")
            if path not in paths or not number.isdigit():continue
            found.setdefault(path,[]).append((path,int(number),line[:155]))
    picked=[found[path][j] for j in range(8) for path in paths if j<len(found.get(path,[]))][:8]
    rendered=[]
    for path,number,line in picked:
        rec=dict(id=len(history)+1,path=path,line=number)
        history.append(rec);rendered.append(f"H{rec['id']} {path}:{number}: {line}")
    text="Literal search "+json.dumps(query,ensure_ascii=False)+":\n"+("\n".join(rendered) if rendered else "(no matches or invalid literal)")
    return text,history[-len(picked)] if picked else None,time.monotonic()-t
def view(work,paths,path,line):
    t=time.monotonic()
    if path not in paths or type(line)!=int or line<1:
        return "Invalid read address",None,time.monotonic()-t
    rows=(work/path).read_text("utf8",errors="replace").splitlines()
    if line>len(rows):return "Invalid read address",None,time.monotonic()-t
    start=max(1,line-9);end=min(len(rows),start+27)
    # Add only complete lines, including the requested line whenever a long prefix would otherwise hide it.
    while start<line and len(tok().encode("\n".join(rows[start-1:line]),add_special_tokens=False).ids)>470:
        start+=1
    def render(tail):return f"{path} lines {start}-{tail}:\n"+"\n".join(rows[start-1:tail])
    while end>line and len(tok().encode(render(end),add_special_tokens=False).ids)>470:end-=1
    text=render(end)
    if len(tok().encode(text,add_special_tokens=False).ids)>470:
        return shorten(text,470),dict(path=path,center=line,start=start,end=end,truncated=True),time.monotonic()-t
    return text,dict(path=path,center=line,start=start,end=end,truncated=False),time.monotonic()-t
def do(i,alias,shared):
    cfg=read(D/"tasks"/i/"public_input.json.gz");work=D/"tasks"/i/"base";paths=cfg["paths"]
    history=[dict(h) for h in shared["history"]];ptr=shared["ptr"];entries=[shared["entry"]]
    log=[];keys=[shared["key"]];tool_s=shared["tool_s"]
    for step in range(2):
        prompt=issuehead(cfg)+"\n\nTool observations:\n"+"\n\n".join(entries)+f"\n\nTool actions left: {2-step}."
        if alias=="evidence" and ptr is not None:
            prompt+=f"\nSaved search address: H{ptr['id']} {ptr['path']}:{ptr['line']}."
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
def infer():
    ids=check();assign={}
    for i in ids:
        cfg=read(D/"tasks"/i/"public_input.json.gz");work=D/"tasks"/i/"base"
        assert all(filehash(work/k)==v for k,v in cfg["files"].items())
        k,ans=call(i,"search",SEARCH,issuehead(cfg),80);history=[]
        query=obj(ans).get("search");entry,pointer,t=search(work,cfg["paths"],query,history)
        shared=dict(key=k,entry=entry,history=history,ptr=pointer,query=query,tool_s=t)
        assign[i]={}
        for alias in sorted(METHODS,key=lambda a:sh((i+a+"|r8").encode())):
            assign[i][alias]=do(i,alias,shared)
            print(i,alias,"done",flush=True)
    write(D/"assign.json",assign)
    files=list((D/"calls").glob("*.json.gz"))+[D/"assign.json"]
    files += [D/"tasks"/i/(method+".json.gz") for i in ids for method in METHODS]
    write(D/"answer_lock.json",{"input":filehash(D/"input_lock.json"),"files":{p.relative_to(D).as_posix():filehash(p) for p in files}})
if __name__=="__main__":
    if sys.argv[1]=="freeze":freeze()
    elif sys.argv[1]=="extract":
        with concurrent.futures.ThreadPoolExecutor(3) as ex:list(ex.map(extract,check()))
    elif sys.argv[1]=="infer":infer()

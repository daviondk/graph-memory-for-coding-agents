"""Project a public SWE-agent *.traj into editor observations and structured, paired tool arguments."""
import collections,concurrent.futures,difflib,gzip,hashlib,json,re,sys,time,urllib.error,urllib.parse,urllib.request,zlib
from pathlib import Path
D=Path(__file__).resolve().parent;P=D.parents[1]/"memory_session5/packets";sys.path.insert(0,str(P))
from common import rel,printed,success
RUN="20250522_sweagent_claude-4-sonnet-20250514"
S3="https://swe-bench-submissions.s3.amazonaws.com/verified/"+RUN+"/trajs/"
LIMIT=48*1024*1024
BAD=re.compile(r"\b(?:CVE[- ]?\d*|exploit(?:ation)?|vulnerabilit\w*|intrusion|payload injection|SQL injection|remote code execution|command injection|deserialization attack|privilege escalation|cross.site scripting|XSS|arbitrary code execution|shellcode|malware|sandbox escape|auth bypass|bioweapon|anthrax|ammunition)\b",re.I)
def h(data):return hashlib.sha256(data).hexdigest()
def save(n,x):(D/n).write_text(json.dumps(x,ensure_ascii=True,indent=1),encoding="utf8")
def canon(x):return str(x).replace("\r\n","\n").strip()
def text(x):
    if isinstance(x,str):return x
    if isinstance(x,list):return "\n".join(v["text"] for v in x if isinstance(v,dict) and isinstance(v.get("text"),str))
    return ""
def project(src,meta):
    traj=src.get("trajectory",[]);hist=src.get("history",[])
    calls=[m for m in hist if m.get("role")=="assistant" and "action" in m]
    results={}
    for m in hist:
        if m.get("role")!="tool":continue
        for key in m.get("tool_call_ids",[]):results.setdefault(key,[]).append(text(m.get("content")))
    ta=[canon(z.get("action","")) for z in traj];ha=[canon(m.get("action","")) for m in calls]
    match={}
    for a,b,n in difflib.SequenceMatcher(a=ta,b=ha,autojunk=False).get_matching_blocks():
        for k in range(n):match[a+k]=b+k
    counts=collections.Counter(steps=len(traj),matched_actions=len(match));ev=[];verify=[]
    for j,step in enumerate(traj):
        act=ta[j];is_editor=bool(re.match(r"^(?:str_replace_editor|str_replace_based_edit_tool|edit_file)\s",act))
        if not is_editor:
            ev.append(["other",{},""]);counts["opaque"]+=1;continue
        m=calls[match[j]] if j in match else {};tt=m.get("tool_calls",[]) or []
        if len(tt)!=1:
            counts["missing_editor_pair"]+=1;return None,counts
        tc=tt[0];f=tc["function"];name=f["name"]
        if name not in ("str_replace_editor","str_replace_based_edit_tool","edit_file") or len(results.get(tc["id"],[]))!=1:
            counts["missing_editor_pair"]+=1;return None,counts
        args=f["arguments"];args=json.loads(args) if isinstance(args,str) else args
        cmd=args.get("command","");path=rel(args.get("path"))
        if not path:ev.append(["other",{},""]);counts["outside"]+=1;continue
        if any(BAD.search(str(v)) for v in [path,args.get("old_str",""),args.get("new_str","")]):
            counts["unsafe_projection"]+=1;return None,counts
        obs=step.get("observation","");display=results[tc["id"]][0]
        rawlines=printed(obs);displaylines=printed(display)
        agree={n:s for n,s in rawlines.items() if n in displaylines and displaylines[n]==s}
        counts["common_lines"]+=len(agree);counts["only_raw_or_changed"]+=len(rawlines)-len(agree);counts["only_display_or_changed"]+=len(displaylines)-len(agree)
        ok=success(cmd,path,obs);ok2=success(cmd,path,display)
        if ok!=ok2:
            counts["success_conflict"]+=1;return None,counts
        cmd_count="cmd_"+cmd;counts[cmd_count]+=1
        if cmd=="str_replace":counts["accepted" if ok else "rejected"]+=1
        if cmd=="view" and agree:counts["documented_views"]+=1
        only={k:args[k] for k in ("path","command","old_str","new_str") if k in args}
        clean=("The file snapshot has been edited.\n" if ok else "")+"\n".join(str(n)+"\t"+s for n,s in sorted(agree.items()))
        ev.append([name,only,clean])
        verify.append([j+1,name,cmd,path,len(rawlines),len(displaylines),len(agree),ok,h(canon(act).encode()),h(tc["id"].encode())])
    counts["editor_pairs"]=len(verify)
    return {"instance":meta["instance_id"],"official_repo":meta["repo"],"base_commit":meta["base_commit"],"issue":meta["problem_statement"],"events":ev,"format":"sweagent-native","pair_projection":verify},counts
def download(meta):
    i=meta["instance_id"];url=S3+i+"/"+i+".traj";receipt={"id":i,"url":url}
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"SWE-memory-research-public-artifact"})
            with urllib.request.urlopen(req,timeout=65) as res:
                size=int(res.headers.get("content-length",-1));receipt.update(content_length=size,etag=res.headers.get("ETag"))
                if size>LIMIT:return (None,{**receipt,"status":"over_size_cap"})
                raw=res.read(LIMIT+1)
                if len(raw)>LIMIT:return None,{**receipt,"status":"over_size_cap"}
                if size>=0 and size!=len(raw):raise OSError("partial download")
            receipt["source_sha256"]=h(raw);receipt["bytes"]=len(raw)
            src=json.loads(raw);del raw
            projected,counts=project(src,meta);del src
            if projected is None:return None,{**receipt,"status":"filtered","counts":dict(counts)}
            return projected,{**receipt,"status":"ok","counts":dict(counts)}
        except urllib.error.HTTPError as exc:
            if exc.code in (403,404):return None,{**receipt,"status":"HTTP_"+str(exc.code)}
            if attempt==2:return None,{**receipt,"status":"HTTP_"+str(exc.code)}
        except (OSError,ValueError,KeyError) as exc:
            if attempt==2:return None,{**receipt,"status":"error_"+type(exc).__name__}
        time.sleep(.4*(attempt+1))
def main():
    all_=json.loads((D/"selection.json").read_bytes());out=[gzip.open(D/f"source_{j}.jsonl.gz","wt",encoding="utf8",compresslevel=3) for j in range(8)]
    rec=[];t=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(7) as pool:
        for n,(p,r) in enumerate(pool.map(download,all_)):
            rec.append(r)
            if p:out[n%8].write(json.dumps(p,separators=(",",":"),ensure_ascii=True)+"\n")
            if (n+1)%16==0:print(n+1,dict(collections.Counter(z["status"] for z in rec)),flush=True)
    for f in out:f.close()
    save("receipts.json",rec);save("download_summary.json",dict(n=len(all_),statuses=dict(collections.Counter(r["status"] for r in rec)),seconds=time.monotonic()-t,sources={f.name:h(f.read_bytes()) for f in sorted(D.glob("source_*.gz"))}))
if __name__=="__main__":main()

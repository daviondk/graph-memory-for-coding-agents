"""Forecast an edit location. Only completed observations reach the predictor."""
import sys,re,importlib.util,hashlib,json,gzip
from collections import defaultdict,Counter
from pathlib import Path
D=Path(__file__).resolve().parent;R=D.parent;AP=R/"action_probe"
sys.path.insert(0,str(AP));spec=importlib.util.spec_from_file_location("terminal_projection",AP/"policy.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.path.insert(0,str(R.parent/"graph_memory_round3/repo/lib"))
from tokenizers import Tokenizer
from infer_action import save,sha
tok=Tokenizer.from_file(str(R.parent/"memory_session5/live/tokenizer.json"))
def ids(s):return tok.encode(s,add_special_tokens=False).ids
def clip(s,n):return s if len(ids(s))<=n else tok.decode(ids(s)[:n],skip_special_tokens=False)
def rr(p):
    with gzip.open(p,"rt",encoding="utf8") as f:yield from map(json.loads,f)
BAD=re.compile(r"\b(?:metasploit|shellcode|ransomware|malware|bioweapon|exploit(?:s|ation)?|privilege escalation|command injection|remote code execution|bypass authentication|deserialization attack)\b",re.I)
def words(s):return {v.lower() for v in re.findall(r"[a-zA-Z_]\w{2,}",s)}-{"this","that","from","with","which","there","error","self","none","when","test","class","true","false","import","return","path","command"}
def groups(entries):
    runs=[]
    for p,n,s,raw in entries:
        if not runs or p!=runs[-1][-1][0] or n!=runs[-1][-1][1]+1 or len(runs[-1])>=6:runs.append([])
        runs[-1].append((p,n,s,raw))
    return runs
def choose(views,query,t,editor_only=False):
    score=lambda v:(len(query&words(v["path"]+" "+v["text"]))/max(1,len(query&words(v["path"]+" "+v["text"]))+4) + .40/(1+(t-v["step"])/4), v["step"],-v["start"])
    candidates=sorted([v for v in views if not editor_only or v["kind"]=="edit"],key=score,reverse=True)
    raw=[];loc=[];seen=set();terminal=0
    for v in candidates:
        key=(v["path"],v["start"],v["text"])
        if key in seen:continue
        a=v["title"]+"\n"+v["text"];b=(v["title"]+("  ["+v["path"]+" lines "+str(v["start"])+"-"+str(v["end"])+"]" if v["kind"]=="shell" else "")+"\n"+v["text"])
        if max(len(ids("\n\n".join([*raw,a]))),len(ids("\n\n".join([*loc,b]))))>900:continue
        raw.append(a);loc.append(b);seen.add(key);terminal+=v["kind"]=="shell"
        if len(raw)>=20:break
    return "\n\n".join(raw) or "(no previous excerpt)","\n\n".join(loc) or "(no previous excerpt)",terminal
def main():
    W=R/"writer";eligible=defaultdict(list)
    for iid,cut,*_ in rr(W/"headroom.jsonl.gz"):eligible[iid].append(cut)
    selected={iid:min(cuts,key=lambda c:sha("r5-edit-cut|"+iid+"|"+str(c))) for iid,cuts in eligible.items()}
    tasks=(q for k in range(8) for q in rr(W/("source_"+str(k)+".jsonl.gz")))
    out=[];skipped=[]
    for task,(iid,raws) in zip(tasks,rr(AP/"raw_pairs.jsonl.gz"),strict=True):
        assert task["instance"]==iid
        if iid not in selected:continue
        t=selected[iid];history=[];views=[];root=True;last=None;issue=clip(task["issue"],700);q=words(issue)
        for step,(observable,extra) in enumerate(zip(task["events"][:t],raws[:t]),1):
            tool,args,obs=observable;p=m.anchor.rel(args.get("path"));cmd=args.get("command","")
            if tool=="str_replace_editor":
                history.append(str(step)+": editor "+str(cmd)+" "+str(p or ""))
                for run in groups([(p,n,s,str(n)+"\t"+s) for n,s in sorted(m.anchor.printed(obs).items()) if p]):
                    v=dict(kind="edit",path=p,start=run[0][1],end=run[-1][1],step=step,title="Editor "+p,text="\n".join(z[3] for z in run));views.append(v);last=(p,run[0][1])
            elif extra and extra["name"]=="bash":
                command=extra["command"]
                if not isinstance(command,str):continue
                added=m.readlines(extra,root)
                history.append(str(step)+": terminal"+(" read" if added else " action"))
                chunks=[s for start,stop,vs in extra["pieces"] for s in vs];lookup=defaultdict(list)
                for s in chunks:
                    match=m.NAMED.match(s) or m.NUMBER.match(s) or m.GREP.match(s)
                    if match:lookup[match.groups()[-1]].append(s)
                for run in groups([(f,n,s,(s if meth=="literal_range" else next((v for v in lookup.get(s,[]) if re.search(r"(?<!\d)"+str(n)+r"(?!\d)",v)),s))) for f,n,s,meth in added]):
                    p=run[0][0];v=dict(kind="shell",path=p,start=run[0][1],end=run[-1][1],step=step,title="$ "+command,text="\n".join(z[3] for z in run));views.append(v);last=(p,run[0][1])
                if re.search(r"(?:^|[;&\n])\s*(?:cd|pushd|popd)\b",command):root=False
                if re.fullmatch(r"\s*cd\s+/testbed/?\s*",command):root=True
        flat,mapped,n=choose(views,q,t);editor,_,_=choose(views,q,t,True)
        ctx="Issue:\n"+issue+"\n\nCompleted actions:\n"+"\n".join(history[-8:])
        if BAD.search("\n".join([iid,ctx,flat,mapped,editor])):skipped.append(iid);continue
        facts={"editor":editor,"terminal":flat,"address":mapped}
        out.append(dict(id=iid+"|"+str(t),instance=iid,repo=task["official_repo"],cut=t,ctx=ctx,snippets={k:[v,len(ids(v))] for k,v in facts.items()},n_terminal=n,last_address=last))
    out=sorted(out,key=lambda x:sha("r5-edit-task|"+x["instance"]))[:96]
    save("H_packets.json.gz",out)
    names=["prepare.py","infer_action.py","PROTOCOL_RU.md","H_packets.json.gz"]
    save("H_data_lock.json",{"sha":{n:sha((D/n).read_bytes()) for n in names},"upstream_policy_sha":sha((AP/"policy.py").read_bytes()),"events":sha((AP/"raw_pairs.jsonl.gz").read_bytes()),"n":len(out),"projects":len({x["repo"] for x in out}),"changed":sum(x["snippets"]["address"]!=x["snippets"]["terminal"] for x in out),"skipped":skipped,"eligible_tasks":len(eligible)})
    print("Prepared",len(out),flush=True)
if __name__=="__main__":main()


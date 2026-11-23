"""Preregistered stratified, issue-disjoint selection. Reads static public samples; never executes their contents."""
import sys,gzip,json,random,hashlib,re
from collections import Counter,defaultdict
from pathlib import Path
D=Path(__file__).resolve().parent;W=D.parents[1];S=W/"graph_memory_round15/test_receipts"
sys.path.insert(0,str(S))
import collect as old
from receipt_policy import terminal,COUNTER,TIMER
def sha(x):return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()
def save(n,v):
    b=json.dumps(v,sort_keys=True,indent=None if n.endswith(".gz") else 2,ensure_ascii=False).encode()
    (D/n).write_bytes(gzip.compress(b,mtime=0) if n.endswith(".gz") else b)
REPOS=["aio-libs/aiohttp","HTTP-APIs/hydrus","systemd/mkosi","vyperlang/vyper"]
BAD=re.compile(r"\b(?:CVE|securit\w*|crypto\w*|password\w*|authenticat\w*|authoriz\w*|exploit\w*|vulnerab\w*|malicious|denial of service|stack overflow|buffer overflow|xss|injection|request smuggling|sandbox escape|symlink attack|traversal|csrf|reentranc\w*)\b",re.I)
SEL=re.compile(r"(?:[A-Za-z0-9_-]+/)*(?:test_[A-Za-z0-9_-]+|[A-Za-z0-9_-]+_test)\.py(?:::[A-Za-z0-9_]+)*$")
FLAGS={"--disable-warnings","--disable-pytest-warnings","--no-header","--no-summary","--show-capture=no","--color=no","--maxfail=1","--maxfail=2","--maxfail=3"}
def selector(kind,repo):
    args=kind["args"]
    p=next((i for i,s in enumerate(args) if s.rsplit("/",1)[-1] in ("pytest","py.test")),None)
    if p is None:return
    paths=[]
    for a in args[p+1:]:
        if a in FLAGS or re.fullmatch(r"-(?:[qvxrsWl]+|r[aAxXfEpsw]+)|--tb=(?:short|line|long|auto|no|native)",a):continue
        a=a.removeprefix("./")
        for prefix in ("/testbed/", "/"+repo.split("/")[-1]+"/"):
            if a.lower().startswith(prefix.lower()):a=a[len(prefix):]
        if not SEL.fullmatch(a) or BAD.search(a.replace("_"," ")):return
        paths.append(a)
    if len(paths)==1:return paths[0]
def suffix(t,n):
    return t.encode()[-n:].decode("utf8",errors="ignore")
def stats(line,state):
    if state=="no_evidence":return None
    m=TIMER.fullmatch(line.strip("= "))
    if m is None:return None
    c={}
    for part in m[1].split(","):
        a=COUNTER.fullmatch(part.strip())
        if a:c[(("subtest " if a[2] else "")+a[3])]=int(a[1])
    return c
def main():
    assert not (D/"assignment.lock.json").exists()
    ct=Counter();sources={};rows=[]; candidates=defaultdict(list);costs={}
    for repo in REPOS:
        for f in sorted((old.upstream.H/repo.replace("/","__")).glob("*/*.traj.json")):
            ct["files"]+=1;b=f.read_bytes();data=json.loads(b);ms=data["messages"];iid=f.parent.name
            user=next((m.get("content","") for m in ms if m.get("role")=="user"),"")
            if old.BAD.search(user.partition("</pr_description>")[0]) or BAD.search(user.partition("</pr_description>")[0]):ct["filtered_issue"]+=1;continue
            sources[f.relative_to(old.upstream.H.parent.parent).as_posix()]=sha(b)
            for step,cmd,reply in old.upstream.pairs(ms):
                if not re.search(r"\b(?:pytest|py\.test)\b",cmd) or BAD.search(cmd.replace("_"," ")):continue
                k=old.parse(cmd)
                if not k:continue
                sel=selector(k,repo)
                if not sel:continue
                rc=reply.get("extra",{}).get("returncode");wm=old.WRAP.fullmatch(reply.get("content",""))
                if not wm or type(rc)!=int or int(wm[1])!=rc:continue
                v=wm[2].strip("\r\n"); st,line=terminal(v)
                row=dict(repo=repo,iid=iid,step=step,call=reply["tool_call_id"],rc=rc,shape=k["shape"],cmd=cmd,selector=sel,
                         visible=v,state=st,last=line,id=sha(repo+"|"+iid+"|"+str(step))[:20],counts=stats(line,st))
                rows.append(row);ct["candidates"]+=1
    choices=defaultdict(set)
    for row in rows:choices[(row["repo"],row["iid"])].add(row["selector"]);choices[(row["repo"],"")].add(row["selector"])
    def diff(row,key):
        a=[s for s in choices[key] if s.split("::")[0]!=row["selector"].split("::")[0]]
        return min(a,key=lambda s:sha("other file 1601|"+row["id"]+"|"+s),default=None)
    for row in rows:
        if row["state"]=="pass":
            candidates["positive"].append((row,row["selector"],"same"))
            target=diff(row,(row["repo"],row["iid"]));origin="same_issue"
            if not target:target=diff(row,(row["repo"],""));origin="same_repo"
            if target:candidates["wrong_scope"].append((row,target,origin))
        else:candidates["negative" if row["state"]=="fail" else "unverified"].append((row,row["selector"],"same"))
    classes=["positive","negative","unverified","wrong_scope"]
    ranked={s:sorted(candidates[s],key=lambda x:sha("draw 1601|"+s+"|"+x[0]["id"])) for s in classes}
    chosen=[];used=set()
    for i in range(8):
        for c in classes:
            for row,to,origin in ranked[c]:
                u=(row["repo"],row["iid"])
                if u not in used:
                    used.add(u);chosen.append(dict(row,query=to,target_origin=origin,design=c));break
    blind=[];ass=[];prompts=[];key={}
    for row in chosen:
        uid=sha("record/16/"+row["id"])[:16];source_id=sha("evidence/"+row["id"])[:14]
        card=sha("independent auditor 1601|"+row["id"])[:12]
        key[card]=uid
        # Full stdout available to adjudicator, independently of the shorter model input.
        blind.append({"card":card,"query":row["query"],"ran":row["selector"],"console_tail":suffix(row["visible"],4000)})
        ass.append(dict(row,uid=uid,blind_id=card));rec=suffix(row["visible"],768)
        source_line=row["last"] if row["state"]!="no_evidence" else ""
        payload={"counts":row["counts"],"summary_emitted":row["counts"] is not None,"event":source_id}
        if source_line:payload["line_fingerprint"]=sha(source_line)[:16]
        info={"shell":"","raw":rec,"parser":source_line,"structured":json.dumps(payload,sort_keys=True,separators=(",",":"))}
        for arm,body in info.items():
            body=suffix(body,768)
            prompt={"checkpoint":source_id,"requested_pytest_selector":row["query"],"observed_pytest_selector":row["selector"],
                   "shell_form":row["shape"],"shell_returncode":row["rc"],"observation":body}
            prompts.append(dict(uid=uid,arm=arm,fields=prompt,payload_bytes=len(body.encode())))
    prompts.sort(key=lambda x:sha("order 1601|"+x["uid"]+"|"+x["arm"]))
    save("blind-cards.json",sorted(blind,key=lambda x:x["card"]));save("assignment.gz",ass);save("prompts.gz",prompts)
    save("cohort.json",{"repositories":REPOS,"counts":ct,"candidate_events":{c:len(ranked[c]) for c in classes},"chosen":len(chosen),
                        "chosen_by_stratum":Counter(r["design"] for r in chosen),"source_sha256":sources,
                        "snapshot":"11164976b4f920cdb0d0cd570ca572e49acea1e8"})
    names=["PROTOCOL_RU.md","prepare.py","run_local.py","score_actions.py","assignment.gz","prompts.gz","blind-cards.json","cohort.json"]
    save("assignment.lock.json",{n:sha((D/n).read_bytes()) for n in names})
    print(json.dumps({"eligible":ct,"selected":len(chosen),"by_stratum":Counter(r["design"] for r in chosen),"by_repo":Counter(r["repo"] for r in chosen)}))
if __name__=="__main__":main()

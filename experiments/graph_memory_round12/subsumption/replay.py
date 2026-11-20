"""Prospective per-tool prefix decisions using the published Vibe transcripts; no shell execution."""
import collections,gzip,hashlib,importlib.util,json,re,shlex,sys
from pathlib import Path
D=Path(__file__).resolve().parent
EXT=D.parent/"negative_external"
spec=importlib.util.spec_from_file_location("parser",EXT/"extract.py");parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
def sha(b):return hashlib.sha256(b).hexdigest()
def save(n,x):
    data=(json.dumps(x,ensure_ascii=False,indent=None if n.endswith(".gz") else 2,sort_keys=True)+"\n").encode()
    (D/n).write_bytes(gzip.compress(data,mtime=0) if n.endswith(".gz") else data)
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def query(cmd,root,attested):
    if (not attested and not cmd.lstrip().startswith("cd /")) or re.search(r"(?:-m\s*0\b|--max-count|-R|--follow|--hidden|--null)",cmd):return
    x,why=parser.parse(cmd,"/testbed",root)
    if not x:return
    stripped=re.sub(r"^cd\s+[^&]+&&\s*","",cmd.strip())
    try:tokens=shlex.split(stripped)
    except ValueError:return
    # Canonicalize switches whose traversal or binary behavior can alter existence.
    binary=any(a.startswith("-") and not a.startswith("--") and "I" in a for a in tokens)
    if any(a.startswith("-") and not a.startswith("--") and "R" in a for a in tokens):return
    return dict(x,binary=binary)
def observation(row):
    extra=row.get("extra") or {};shown=parser.EXIT.fullmatch(row.get("content",""));num=extra.get("returncode");raw=extra.get("raw_output")
    if not shown or type(num)!=int or int(shown[1])!=num or not isinstance(raw,str) or extra.get("exception_info"):return "unknown"
    if num==1 and not shown[2].strip() and not raw.strip():return "empty"
    if num==0:return "found"
    return "error"
def conservative_read(cmd):
    # Omitted pipelines, redirection, arbitrary interpreters and ambiguous switches are fences.
    if any(z in cmd for z in (";","|","&",">","<",chr(96),"$","\n","\x00")):return False
    try:t=shlex.split(cmd)
    except ValueError:return False
    if not t:return False
    if t[0]=="pwd":return len(t)==1
    if t[0] in ("cat","head","tail","ls"):
        return all(re.fullmatch(r"[-./A-Za-z0-9_+:]+",v) for v in t[1:])
    if t[0]=="sed":return len(t)==4 and t[1]=="-n" and bool(re.fullmatch(r"(?:\d+|\$)(?:,(?:\d+|\$))?p",t[2]))
    return False
def sufficient(old,new,narrow=False):
    if any(old[k]!=new[k] for k in ("root","tool","binary","oi")):return False
    a=old["literal"];b=new["literal"]
    if old["oi"]:a=a.lower();b=b.lower()
    if old["word"]:
        if not new["word"] or a!=b:return False
    elif a not in b:return False
    if old["globs"] and (not new["globs"] or not set(new["globs"])<=set(old["globs"])):return False
    p,q=old["scope"],new["scope"]
    if p==q:return old["recurse"] or not new["recurse"]
    # git-grep has tracked directory semantics. GNU grep/rg can skip hidden or ignored descendants
    # that an explicit narrower path would include. Decline all such cross-path claims.
    return narrow and old["tool"]=="git-grep" and old["recurse"] and (p=="." or q.startswith(p+"/"))
def predict():
    roster=read(EXT/"roster.json");out=[];truth=[];stats=collections.Counter();sets=collections.defaultdict(set)
    for rec in roster:
        path=parser.V/"benchmark"/rec["file"];raw=path.read_bytes();assert sha(raw)==rec["sha"]
        messages=json.loads(raw)["messages"];user=next(m["content"] for m in messages if m.get("role")=="user")
        attested="/testbed (this is the working directory" in user or "working directory is /testbed" in user
        root=parser.source(rec["repo"]);pending={};seen={};registries={g:[] for g in ("strict","session")};scopes={g:set() for g in registries}
        for step,m in enumerate(messages):
            if m.get("role")=="assistant":
                calls=m.get("tool_calls") or []
                if pending or len(calls)>1:
                    registries["strict"].clear();scopes["strict"].clear()
                for call in calls:
                    fn=call.get("function",{});args=fn.get("arguments")
                    try:arg=json.loads(args) if isinstance(args,str) else args
                    except ValueError:arg={}
                    cmd=arg.get("command") if isinstance(arg,dict) and fn.get("name")=="bash" else None
                    key=query(cmd,root,attested) if isinstance(cmd,str) else None
                    if len(calls)>1:key=None
                    if not key and (not isinstance(cmd,str) or not conservative_read(cmd)):
                        registries["strict"].clear();scopes["strict"].clear();stats["fences"]+=1
                    if fn.get("name")=="bash":stats["bash"]+=1
                    if not call.get("id"):continue
                    if key:
                        stats["eligible"]+=1
                        pred={};sources={}
                        for g,old in registries.items():
                            for arm in ("literal_command","equivalent","same_scope","known_scope","any_scope"):
                                for s,original,r in reversed(old):
                                    if arm=="literal_command":good=cmd==original and key==r
                                    elif arm=="equivalent":good=key==r
                                    else:
                                        known=(key["root"],key["scope"]) in scopes[g]
                                        good=sufficient(r,key,narrow=arm=="any_scope" or (arm=="known_scope" and known))
                                    if good:
                                        pred[g+"|"+arm]=True;sources[g+"|"+arm]=s;break
                        out.append(dict(iid=rec["iid"],repo=rec["repo"],step=step,call=call["id"],key=key,source=sources));sets["eligible_tasks"].add(rec["iid"])
                    pending[call["id"]]=(step,cmd,key)
            elif m.get("role")=="tool":
                cid=m.get("tool_call_id")
                if cid not in pending:
                    registries["strict"].clear();scopes["strict"].clear();continue
                step0,cmd,key=pending.pop(cid)
                if key:
                    kind=observation(m)
                    truth.append(dict(iid=rec["iid"],step=step0,call=cid,label=kind))
                    if kind in ("found","empty"):
                        for s in scopes.values():s.add((key["root"],key["scope"]))
                    if kind=="empty":
                        for old in registries.values():old.append((step0,cmd,key))
    assert len({(r["iid"],r["step"],r["call"]) for r in out})==len(out)
    save("forecasts.gz",out);save("oracle.gz",truth)
    save("lock.json",dict(files={f:sha((D/f).read_bytes()) for f in ("PROTOCOL_RU.md","replay.py","forecasts.gz","oracle.gz")},
        input_sha=sha((EXT/"roster.json").read_bytes()),parser=sha((EXT/"extract.py").read_bytes()),
        counts={**stats,"tasks":len(roster),"eligible_tasks":len(sets["eligible_tasks"])}))
def grade():
    lock=read(D/"lock.json");assert all(sha((D/n).read_bytes())==h for n,h in lock["files"].items())
    truths={(r["iid"],r["step"],r["call"]):r["label"] for r in read(D/"oracle.gz")}
    spec=read(D/"forecasts.gz");results={};ledger=[]
    for g in ("strict","session"):
        for arm in ("literal_command","equivalent","same_scope","known_scope","any_scope"):
            key=g+"|"+arm;counts=collections.Counter();groups=set()
            for r in spec:
                if key not in r["source"]:continue
                label=truths.get((r["iid"],r["step"],r["call"]),"unknown");counts[label]+=1;groups.add(r["iid"])
                ledger.append(dict(iid=r["iid"],repo=r["repo"],query=r["key"],step=r["step"],previous=r["source"][key],arm=key,actual=label))
            results[key]=dict(counts=counts,issued=sum(counts.values()),tasks=len(groups))
    save("results.json",dict(counts=lock["counts"],measured=collections.Counter(truths.values()),arms=results))
    save("decisions.gz",ledger)
if __name__=="__main__":{"predict":predict,"grade":grade}[sys.argv[1]]()

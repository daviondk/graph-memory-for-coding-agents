import collections,gzip,hashlib,json,re,sys
from pathlib import Path
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent))
import replay as lib
p=lib.parser
REPOS="adamchainz/flake8-comprehensions python-attrs/attrs ipython/traitlets theacodes/nox scikit-build/scikit-build-core HypothesisWorks/hypothesis Delgan/loguru pallets/click s-knibbs/dataclasses-jsonschema brazilian-utils/brutils-python".split()
WRITE=re.compile(r"(?:\b(?:apply_patch|patch|rm|mv|cp|touch|mkdir|tee)\b|\bsed\s+[-\w]*i\b|\b(?:write_text|write_bytes|write|writelines)\s*\(|\bopen\([^\n)]*,\s*['\x22][wax]|\s>{1,2}(?![=&])|\bgit\s+(?:checkout|reset|restore|apply|clean|merge|rebase|switch)\b)")
PATH=re.compile(r"(?<![\w.-])(?:/?(?:[\w.-]+/)*[\w.-]+\.(?:pyx?|pxd|c|h|md|rb|rs|txt|toml|cfg|json|yaml|yml))\b",re.I)
GROUPS=("session","ttl8","strict","global_write","path_write")
def save(name,v):libdata=(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=None if name.endswith(".gz") else 2)+"\n").encode();(D/name).write_bytes(gzip.compress(libdata,mtime=0) if name.endswith(".gz") else libdata)
def overlap(scope,path):
    path=path.removeprefix("/testbed/").removeprefix("./").strip("/")
    scope=scope.removeprefix("./").strip("/")
    return scope=="." or path==scope or path.startswith(scope+"/") or scope.startswith(path+"/") or path.endswith("/"+scope)
def new_roster():
    official=lib.read(p.V/"memory-stage-fetch/source-manifest.json")
    registered={x["rfilename"]:x for x in official["siblings"]};ret=[]
    for repo in REPOS:
        folder=p.H/repo.replace("/","__")
        assert folder.is_dir(),repo
        for f in sorted(folder.glob("*/*.traj.json")):
            b=f.read_bytes();k=f.relative_to(p.V/"benchmark").as_posix();s=registered[k];h=s.get("lfs",{}).get("sha256") or s["blobId"]
            assert (lib.sha(b) if len(h)==64 else hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest())==h
            m=json.loads(b)["messages"];user=next(x["content"] for x in m if x["role"]=="user")
            if p.BAD.search(user.partition("</pr_description>")[0]):continue
            ret.append(dict(iid=f.parent.name,repo=repo,file=k,sha=lib.sha(b)))
    return ret
def predict():
    new=new_roster();old=lib.read(lib.EXT/"roster.json");assert not {x["repo"].lower() for x in new}&{x["repo"].lower() for x in old}
    save("new-roster.json",new)
    forecast=[];grades=[]
    counts=collections.Counter()
    for panel,records in (("old",old),("external",new)):
        for r in records:
            data=(p.V/"benchmark"/r["file"]).read_bytes();assert lib.sha(data)==r["sha"]
            msgs=json.loads(data)["messages"];user=next(m["content"] for m in msgs if m["role"]=="user")
            attested="/testbed (this is the working directory" in user or "working directory is /testbed" in user
            roots=p.source(r["repo"]);pending={};cache={g:[] for g in GROUPS};ordinal=0
            for step,m in enumerate(msgs):
                if m.get("role")=="assistant":
                    calls=m.get("tool_calls") or []
                    multi=len(calls)>1 or bool(pending)
                    if multi:
                        for g in GROUPS:
                            if g not in ("session","ttl8"):cache[g].clear()
                    for c in calls:
                        fn=c.get("function",{});args=fn.get("arguments")
                        try:args=json.loads(args) if isinstance(args,str) else args
                        except ValueError:args=None
                        cmd=args.get("command") if isinstance(args,dict) and fn.get("name")=="bash" else None
                        ordinal+=1
                        key=lib.query(cmd,roots,attested) if isinstance(cmd,str) and not multi else None
                        if not key and (not isinstance(cmd,str) or not lib.conservative_read(cmd)):
                            cache["strict"].clear()
                            if not isinstance(cmd,str) or WRITE.search(cmd):
                                cache["global_write"].clear()
                                paths=PATH.findall(cmd or "")
                                cache["path_write"]=[v for v in cache["path_write"] if paths and not any(overlap(v[2]["scope"],x) for x in paths)]
                        cache["ttl8"]=[v for v in cache["ttl8"] if ordinal-v[0]<=8]
                        if not c.get("id"):continue
                        if key:
                            counts[panel+" eligible"]+=1;src={}
                            for g in GROUPS:
                                for a in ("equivalent","same_scope"):
                                    for _,s,k in reversed(cache[g]):
                                        good=(k==key) if a=="equivalent" else lib.sufficient(k,key)
                                        if good:src[g+"|"+a]=s;break
                            forecast.append(dict(panel=panel,iid=r["iid"],repo=r["repo"],step=step,call=c["id"],sources=src))
                        pending[c["id"]]=(ordinal,step,key)
                elif m.get("role")=="tool":
                    cid=m.get("tool_call_id")
                    if cid not in pending:
                        for g in ("strict","global_write","path_write"):cache[g].clear()
                        continue
                    ix,step0,key=pending.pop(cid)
                    if key:
                        label=lib.observation(m)
                        grades.append(dict(panel=panel,iid=r["iid"],step=step0,call=cid,label=label))
                        if label=="empty":
                            for rr in cache.values():rr.append((ix,step0,key))
    save("forecast.gz",forecast);save("oracle.gz",grades)
    save("lock.json",dict(old=len(old),external=len(new),counts=counts,files={n:lib.sha((D/n).read_bytes()) for n in ("scope.py","PROTOCOL_RU.md","new-roster.json","forecast.gz","oracle.gz")}))
def grade():
    lock=lib.read(D/"lock.json");assert all(lib.sha((D/n).read_bytes())==h for n,h in lock["files"].items())
    oracle={(x["panel"],x["iid"],x["step"],x["call"]):x["label"] for x in lib.read(D/"oracle.gz")}
    out=collections.defaultdict(collections.Counter);ledger=[]
    for x in lib.read(D/"forecast.gz"):
        for a,s in x["sources"].items():
            truth=oracle.get((x["panel"],x["iid"],x["step"],x["call"]),"unknown")
            out[x["panel"]+"|"+a][truth]+=1
            ledger.append(dict(panel=x["panel"],iid=x["iid"],step=x["step"],previous=s,arm=a,truth=truth))
    save("results.json",dict(old=lock["old"],external=lock["external"],counts=lock["counts"],arms=out));save("pairs.gz",ledger)
if __name__=="__main__":{"predict":predict,"grade":grade}[sys.argv[1]]()

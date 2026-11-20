"""Post-lock evaluation against published merge parent and real next read, reusing R13 semantics."""
import collections
import concurrent.futures
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys

D = Path(__file__).resolve().parent
R13 = D.parents[1] / "graph_memory_round13/reformulation"
sys.path.insert(0, str(R13))
import prefix, pr_oracle
CACHE = Path("D:/CodexResearch/x20-round14-grounded-objects")
ARMS = ("none", "recommend", "pair", "named")
def h(b):return hashlib.sha256(b).hexdigest()
def read(n):
    raw=(D/n).read_bytes()
    if n.endswith(".jsonl"):return [json.loads(s) for s in raw.splitlines()]
    return json.loads(gzip.decompress(raw) if n.endswith(".gz") else raw)
def save(n,data):
    raw=json.dumps(data,sort_keys=True,ensure_ascii=False,indent=1).encode("utf8")
    (D/n).write_bytes(gzip.compress(raw,mtime=0) if n.endswith(".gz") else raw)
def locks():
    for lock in ("read-lock.json","action-lock.json","assignment.json"):
        obj=read(lock);files=obj["files"] if lock=="assignment.json" else obj
        for n,sha in files.items():assert h((D/n).read_bytes())==sha,(lock,n)
    for n,value in read("assignment.json")["borrowed"].items():assert h((R13/n).read_bytes())==value

def patches(cases):
    # The original R13 formatter resolves PR HTML and reads immutable Git parents and diffs.
    prefix.D = pr_oracle.D = D
    pr_oracle.CACHE = CACHE
    (D/"pr_refs").mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(5) as pool:
        refs=list(pool.map(pr_oracle.meta,[(c["iid"],c["repo"]) for c in cases]))
    by=collections.defaultdict(list)
    for c,r in zip(cases,refs):
        assert c["iid"]==r["iid"]
        r["base"]=c["base"]
        if r["status"]=="ok":by[r["repo"]].append(r)
    def safe(group):
        try:return pr_oracle.fetch(group)
        except (OSError,RuntimeError,subprocess.SubprocessError,IndexError) as exc:
            for r in group[1]:
                try:pr_oracle.fetch((group[0],[r]))
                except (OSError,RuntimeError,subprocess.SubprocessError,IndexError) as sub:
                    r.update(status="git_unavailable",git_error=str(sub)[:350])
    with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(safe,by.items()))
    save("patch_labels.gz",refs)
    return {r["iid"]:r for r in refs}
def navigation(cases):
    original={r["iid"]:r for r in read("roster.json")};out={}
    for c in cases:
        raw=(prefix.V/"benchmark"/original[c["iid"]]["file"]).read_bytes()
        assert h(raw)==original[c["iid"]]["sha"]
        steps=list(prefix.calls(json.loads(raw)["messages"]));start=c["step"]
        assert steps[start][2]==c["id"].split("|",1)[1]
        events=[]
        for i,mi,cid,cmd,tool in steps[start+1:start+6]:
            rc,shown=prefix.shown(tool)
            if rc!=0 or not shown:continue
            found=prefix.inspect(cmd,shown,c["repo"])
            if len(found)!=1:continue
            root,p,kind,lines=found[0]
            if kind=="grep-list" or root!=c["search"]["root"]:continue
            events.append({"delta":i-start,"path":p,"kind":kind,"call":cid,"command":cmd,"visible_sha":h(shown.encode()),"raw_sha":h(tool["extra"]["raw_output"].encode())})
        out[c["id"]]={"target":next(iter(events),None),"events":events,"following":min(5,len(steps)-1-start)}
    save("navigation_labels.gz",out);return out

def receipt_check(records):
    by=collections.defaultdict(list)
    for r in records:
        if r["opened"]:by[r["repo"]].append(r)
    def verify(group):
        repo,items=group;mirror=CACHE/(repo.replace("/","__")+".git");mirror.parent.mkdir(exist_ok=True)
        def git(*args,optional=False):
            p=subprocess.run(["git","-C",str(mirror),*args],capture_output=True,timeout=180,env={**os.environ,"GIT_TERMINAL_PROMPT":"0"})
            if p.returncode and not optional:raise ValueError(p.stderr.decode(errors="replace")[-260:])
            return p
        if not mirror.exists():
            subprocess.run(["git","init","--bare",str(mirror)],capture_output=True,check=True)
            git("remote","add","origin","https://github.com/"+repo+".git")
        missing=[cid for cid in sorted({r["base"] for r in items}) if git("cat-file","-e",cid+"^{tree}",optional=True).returncode]
        if missing:git("fetch","--no-tags","--depth=1","--filter=blob:none","origin",*missing)
        keys=sorted({(r["base"],r["path"]) for r in items});ids={}
        for base,path in keys:
            oid=git("rev-parse",base+":"+path).stdout.strip().decode();assert len(oid)==40
            ids[base,path]=oid
        # Explicit upload-pack wants against parent remote. One prefetch avoids per-blob lazy fetch.
        git("fetch","--no-tags","--depth=1","--filter=blob:none","origin",*sorted(set(ids.values())),optional=True)
        all_checks={}
        for key,oid in ids.items():
            blob=git("cat-file","blob",oid).stdout
            git_hash=hashlib.sha1(b"blob "+str(len(blob)).encode()+b"\0"+blob).hexdigest()
            assert git_hash==oid
            all_checks[key]=(h(blob),len(blob),oid)
        return [{"id":r["id"],"arm":r["arm"],"sha256":all_checks[r["base"],r["path"]][0],"nbytes":all_checks[r["base"],r["path"]][1],"git_blob":all_checks[r["base"],r["path"]][2],"match":(r["blob"],r["bytes"])==all_checks[r["base"],r["path"]][:2]} for r in items]
    out=[]
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        for rs in pool.map(verify,by.items()):out.extend(rs)
    assert all(r["match"] for r in out)
    save("git_receipt_verification.json",out)
def paired(rows,arm,control,field):
    sample=[r for r in rows if r["arms"][arm][field] is not None]
    z=[int(r["arms"][arm][field])-int(r["arms"][control][field]) for r in sample]
    n=len(z);wins=z.count(1);loss=z.count(-1);disc=wins+loss
    p=min(1.,2*sum(math.comb(disc,i) for i in range(min(wins,loss)+1))/(2**disc)) if disc else 1.
    rr=random.Random(22113);bs=sorted(sum(rr.choices(z,k=n))/n for _ in range(10000)) if n else []
    return {"n":n,"wins":wins,"losses":loss,"ties":n-disc,"delta":sum(z)/n if n else None,"exact_p":p,
            "bootstrap_ci":[bs[249],bs[9749]] if n else None,
            "changed_read":sum(r["arms"][arm]["path"]!=r["arms"][control]["path"] for r in sample)}
def main():
    locks()
    cases=read("cases.gz")
    raw=read("reads.gz");actions=read("model.jsonl")
    ra={(r["id"],r["arm"]):r for r in raw};ac={(r["id"],r["method"]):r for r in actions}
    assert len(cases)*4==len(raw)==len(actions)==len(ra)==len(ac)
    if "--cached-labels" in sys.argv:
        pr={r["iid"]:r for r in read("patch_labels.gz")};nav=read("navigation_labels.gz")
        receipts=read("git_receipt_verification.json")
        assert all(r["match"] for r in receipts)
    else:
        pr=patches(cases);nav=navigation(cases);receipt_check(raw)
    rows=[]
    for c in cases:
        p=pr[c["iid"]];q=nav[c["id"]]["target"]
        status=p["status"] if p["status"]!="ok" else "not_direct" if not p["strict"] else "no_old_production_python" if not p["prod"] else "eligible"
        menu=[item["path"] for item in c["menu"]]
        # Source spans shown to all arms may already mention the identifier even in the pair arm.
        shared_text=c["issue"]+" "+c["search"]["literal"]+" "+" ".join(i["visible_excerpt"] for i in c["menu"])
        tokens=set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*",shared_text.lower()))
        full_user = "Issue:\n"+c["issue"]+"\n\nThe following search returned no match:\n"+json.dumps(c["search"],ensure_ascii=False)
        full_user += "\n\nPreviously addressed files and historical excerpts:\n"+json.dumps(c["menu"],ensure_ascii=False)
        def mentioned(value):
            return c["symbol"].lower() in {x.lower() for x in re.findall(r"[A-Za-z_][A-Za-z_0-9]*",value)}
        common_visible = mentioned(full_user)
        pair_excerpts = sum(mentioned(x["visible_excerpt"]) for x in c["menu"] if x["path"] in c["pair"])
        group={}
        for arm in ARMS:
            a=ac[c["id"],arm];rr=ra[c["id"],arm];chosen=rr["path"] if rr["opened"] else None
            assert a["path"]==rr["path"] and rr["base"]==c["base"]
            group[arm]={"path":chosen,"valid":a["valid"],"opened":rr["opened"],"in_pair":chosen in c["pair"],"graph_top":chosen==c["target"],
                        "patch":chosen in p["prod"] if status=="eligible" else None,"navigation":chosen==q["path"] if q else None,
                        "in_tokens":a["usage"]["prompt_tokens"],"out_tokens":a["usage"]["completion_tokens"],"read_bytes":rr.get("bytes",0),"blob_sha":rr.get("blob")}
        rows.append(dict(id=c["id"],iid=c["iid"],repo=c["repo"],status=status,strict=p.get("strict"),symbol=c["symbol"],
                         symbol_visible_in_prose_or_excerpts=c["symbol"].lower() in tokens,symbol_visible_elsewhere=common_visible,pair_excerpt_mentions=pair_excerpts,pair=c["pair"],graph_top=c["target"],
                         prod=p.get("prod"),next_file=q["path"] if q else None,patch_reachable=(bool(set(menu)&set(p["prod"])) if status=="eligible" else None),
                         pair_reachable=(bool(set(c["pair"])&set(p["prod"])) if status=="eligible" else None),
                         nav_reachable=q["path"] in menu if q else None,arms=group))
    save("outcomes.gz",rows)
    armsum={}
    for arm in ARMS:
        a=[r["arms"][arm] for r in rows]
        armsum[arm]={k:sum(x[k] for x in a if x[k] is not None) for k in ("valid","opened","patch","navigation","in_pair","graph_top","in_tokens","out_tokens","read_bytes")}
    comparisons={}
    for aa,bb in (("named","pair"),("named","recommend"),("named","none"),("recommend","none"),("pair","none")):
        comparisons[aa+"-"+bb]={f:paired(rows,aa,bb,f) for f in ("patch","navigation")}
        comparisons[aa+"-"+bb]["all_choice_changes"]=sum(r["arms"][aa]["path"]!=r["arms"][bb]["path"] for r in rows)
    res={"n":len(rows),"status":dict(collections.Counter(r["status"] for r in rows)),"flow":read("flow.json"),"arms":armsum,"pairs":comparisons,
         "patch_ceiling":sum(r["patch_reachable"] or 0 for r in rows),"pair_ceiling":sum(r["pair_reachable"] or 0 for r in rows),"nav_ceiling":sum(r["nav_reachable"] or 0 for r in rows),
         "pair_excerpt_frequency":dict(collections.Counter(r["pair_excerpt_mentions"] for r in rows)),"symbol_in_common_prose_or_excerpt":sum(r["symbol_visible_in_prose_or_excerpts"] for r in rows),"symbol_already_visible":sum(r["symbol_visible_elsewhere"] for r in rows),"next_n":sum(r["next_file"] is not None for r in rows), "strict_repos":dict(collections.Counter(r["repo"] for r in rows if r["status"]=="eligible")),
         "receipt_sources":dict(collections.Counter(r.get("source","none") for r in raw)),"scoring_files":{"pr_oracle.py":h((R13/"pr_oracle.py").read_bytes()),"prefix.py":h((R13/"prefix.py").read_bytes())}}
    save("results.json",res)
    print(json.dumps({"arms":armsum,"status":res["status"],"primary":comparisons["named-pair"]["patch"]}))
if __name__=="__main__":main()

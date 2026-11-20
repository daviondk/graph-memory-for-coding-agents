"""Resolve two published Git commits per case and fetch immutable tree objects."""
import collections, concurrent.futures, json, os, re, subprocess, time, urllib.request
from pathlib import Path
from harvest import D, get, save, sha
ENV = {**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_OPTIONAL_LOCKS":"0"}
def git(repo,*args,timeout=160,check=True,quiet=False):
    return subprocess.run(["git","-c","credential.interactive=false","-C",str(repo),*args],env=ENV,capture_output=True,timeout=timeout,check=check)
def get_http(url):
    for j in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"x20-aggregate-research","Accept":"application/vnd.github+json"})
            with urllib.request.urlopen(req,timeout=18) as f:return json.load(f)
        except OSError:
            if j==2:raise
            time.sleep(1+j)
def meta(q):
    tag=q["iid"].rsplit("-",1)[1];p=D/"git_metadata"/(q["iid"]+".json");p.parent.mkdir(exist_ok=True)
    if p.exists():return get(p)
    url="https://api.github.com/repos/"+q["repo"]+"/pulls/"+tag
    try:
        native=get_http(url);assert str(native["number"])==tag and native["base"]["repo"]["full_name"].lower()==q["repo"].lower()
        row={"iid":q["iid"],"repo":q["repo"],"base":q["base"],"new":native["merge_commit_sha"],"merged":native["merged"],"pr_url":native["html_url"],"api":url,"head":native["head"]["sha"],"status":"ok" if native["merged"] else "not_merged"}
    except (OSError,ValueError,KeyError,AssertionError) as e:row={"iid":q["iid"],"repo":q["repo"],"base":q["base"],"status":"unavailable","detail":str(e)[:225]}
    save(p,row);return row
def local(repo):return D/"git"/(repo.replace("/","__")+".git")
def fetch(group):
    name,rows=group;root=local(name);root.parent.mkdir(exist_ok=True)
    if not root.exists():
        subprocess.run(["git","init","--bare",str(root)],capture_output=True,check=True)
        git(root,"remote","add","origin","https://github.com/"+name+".git")
        git(root,"config","remote.origin.promisor","true")
        git(root,"config","remote.origin.partialclonefilter","blob:none")
    ids=sorted({r[f] for r in rows for f in ("base","new")})
    for i in ids:assert re.fullmatch("[0-9a-f]{40}",i)
    z=git(root,"fetch","--no-tags","--depth=1","--filter=blob:none","origin",*ids,timeout=230,check=False)
    if z.returncode:raise RuntimeError((name,z.stderr.decode(errors="replace")[-2000:]))
    for i in ids:assert git(root,"rev-parse",i+"^{commit}").stdout.decode().strip()==i
    return {"repo":name,"commits":ids,"stderr":z.stderr.decode(errors="replace")}
if __name__=="__main__":
    lock=get(D/"key_lock.json");assert all(sha((D/n).read_bytes())==h for n,h in lock["files"].items())
    unique={r["iid"]:r for r in get(D/"keys.json")}
    with concurrent.futures.ThreadPoolExecutor(4) as ex:rows=list(ex.map(meta,unique.values()))
    save(D/"git_pairs.json",rows)
    print("pairs",collections.Counter(r["status"] for r in rows),flush=True)
    groups=collections.defaultdict(list)
    for r in rows:
        if r["status"]=="ok":groups[r["repo"]].append(r)
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        out=[]
        for r in ex.map(fetch,groups.items()):out.append(r);print("fetched",r["repo"],flush=True)
    save(D/"git_fetch.json",out)

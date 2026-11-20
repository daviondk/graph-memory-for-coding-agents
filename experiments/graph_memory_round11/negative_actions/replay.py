"""Predict from the changed paths and added diff lines, then run a separate git grep/ls-tree oracle."""
import collections
import fnmatch
import functools
import json
import re
import subprocess
import sys
from pathlib import PurePosixPath

from git_pairs import D, ENV, get, git, local, save, sha
def red(row):
    return {k:row[k] for k in ("iid","panel","repo","step","tier","key","use_next_three")}
def under(path,scope):return scope=="." or path==scope or path.startswith(scope+"/")
def matches_name(pat,name):return fnmatch.fnmatchcase(PurePosixPath(name).name,pat)
def allowed(path,key):
    return under(path,key["scope"]) and (not key.get("globs") or any(matches_name(g,path) for g in key["globs"]))
def relpaths(blob):
    return [name.decode("utf8",errors="surrogateescape") for name in blob.split(b"\0") if name]
def chk_names(lst):assert all("\0" not in p and not p.startswith("-") for p in lst)
def command_paths(scope):
    return ["--",":(literal)"+scope] if scope not in (".","") else ["--"]
@functools.lru_cache(maxsize=None)
def tree_names(repo,rev):
    z=git(local(repo),"ls-tree","-r","-z","--name-only",rev).stdout
    return set(relpaths(z))
@functools.lru_cache(maxsize=None)
def changes(repo,old,new):
    out={}
    for k in ["A","M","D","T"]:
        z=git(local(repo),"diff","--name-only","--no-renames","--diff-filter="+k,"-z",old,new).stdout
        out[k]=relpaths(z)
    return out
def normal_pat(key):
    f=re.I|re.ASCII if key.get("ignore_case") else re.ASCII
    lit=re.escape(key["literal"].encode("ascii"))
    if key.get("whole_word"):lit=b"(?<![A-Za-z0-9_])"+lit+b"(?![A-Za-z0-9_])"
    return re.compile(lit,f)
def add_lines(chunks):
    hunk=False
    for raw in chunks.split(b"\n"):
        if raw.startswith(b"diff --git "):hunk=False
        if raw.startswith(b"@@ "):hunk=True;continue
        if hunk and raw.startswith(b"+"):yield raw[1:]
def predict(note,pair):
    key=note["key"];repo=pair["repo"];a=pair["base"];b=pair["new"]
    diff=changes(repo,a,b);touched={p for v in diff.values() for p in v};in_scope=sorted(p for p in touched if allowed(p,key))
    additions=set(diff["A"])|set(diff["M"])|set(diff["T"])
    if key["kind"]=="path":
        parent=str(PurePosixPath(key["literal"]).parent)
        directory=any(under(p,parent) for p in touched)
        exact=any(under(p,key["literal"]) for p in additions)
        return {"scope":directory,"exact":exact,"changed_repo":bool(touched),"changed_paths":len(touched),"scope_count":sum(under(p,parent) for p in touched),"diff_bytes":0,"hit_paths":[p for p in sorted(additions) if under(p,key["literal"])]}
    if key["kind"]=="name":
        hits=[p for p in additions if allowed(p,key) and PurePosixPath(p).name==key["literal"]]
        return {"scope":bool(in_scope),"exact":bool(hits),"changed_repo":bool(touched),"changed_paths":len(touched),"scope_count":len(in_scope),"diff_bytes":0,"hit_paths":sorted(hits)}
    candidates=sorted(set(in_scope)&additions);chk_names(candidates)
    hits=[];bytes_read=0
    for c in candidates:
        patch=git(local(repo),"diff","--no-renames","--no-textconv","--no-ext-diff","--unified=0",a,b,"--",":(literal)"+c).stdout
        bytes_read+=len(patch)
        if any(normal_pat(key).search(line) for line in add_lines(patch)):hits.append(c)
    return {"scope":bool(in_scope),"exact":bool(hits),"changed_repo":bool(touched),"changed_paths":len(touched),"scope_count":len(in_scope),"diff_bytes":bytes_read,"hit_paths":hits}
def emit_pred():
    seal=get(D/"key_lock.json");assert all(sha((D/f).read_bytes())==d for f,d in seal["files"].items())
    pairs={r["iid"]:r for r in get(D/"git_pairs.json")}
    chosen=[]
    for row in get(D/"keys.json"):
        p=pairs[row["iid"]]
        if p["status"]!="ok":continue
        line=red(row)
        chosen.append({**line,**predict(line,p)})
    # Compare the future-mention policy against an equally sized deterministic subset of the original input roster.
    for panel in set((r["tier"],r["panel"]) for r in chosen):
        grp=[r for r in chosen if (r["tier"],r["panel"])==panel];n=sum(r["use_next_three"] for r in grp)
        group=sorted(grp,key=lambda r:sha(("r11-placebo|"+r["iid"]+"|"+str(r["step"])).encode()))
        for j,r in enumerate(group):r["hash_keep"]=j<n
    save(D/"predictions.json",chosen)
    save(D/"pre_oracle.lock.json",{"files":{k:sha((D/k).read_bytes()) for k in ["replay.py","git_pairs.json","git_fetch.json","key_lock.json","predictions.json"]},"count":len(chosen)})
def grep_run(repo,rev,key):
    names=tree_names(repo,rev)
    if key["kind"]=="path":
        match=sorted(p for p in names if under(p,key["literal"]))
        return {"valid":True,"hit":bool(match),"files":match[:6],"matched_files":len(match)}
    scope=key["scope"]
    scope_files=[p for p in names if under(p,scope)]
    if not scope_files:return {"valid":False,"reason":"scope_missing_from_tracked_tree"}
    if key["kind"]=="name":
        hits=sorted({p for p in scope_files if PurePosixPath(p).name==key["literal"]})
        if not key["regular_only"]:
            hits=sorted(set(hits)|{str(anc) for p in scope_files for anc in PurePosixPath(p).parents if anc.name==key["literal"] and under(str(anc),scope)})
        return {"valid":True,"hit":bool(hits),"files":hits[:6],"matched_files":len(hits)}
    if not key["recurse"] and scope not in names:return {"valid":False,"reason":"nonrecursive_directory"}
    paths=command_paths(scope);opts=["-i"] if key["ignore_case"] else []
    if key["whole_word"]:opts+=["-w"]
    if key["globs"]:
        paths=["--",*([":(glob)"+(scope.rstrip("/")+"/" if scope!="." else "")+"**/"+g for g in key["globs"]])]
    cp=git(local(repo),"grep","-I","-l","-z","-F",*opts,"-e",key["literal"],rev,*paths,check=False,timeout=180)
    if cp.returncode not in [0,1]:raise RuntimeError(cp.stderr.decode(errors="replace")[-1300:])
    hits=[p.removeprefix(rev+":") for p in relpaths(cp.stdout)]
    return {"valid":True,"hit":cp.returncode==0,"files":hits[:6],"matched_files":len(hits),"exit":cp.returncode}
def score():
    lock=get(D/"pre_oracle.lock.json");assert all(sha((D/f).read_bytes())==v for f,v in lock["files"].items())
    rec=get(D/"predictions.json");pairs={r["iid"]:r for r in get(D/"git_pairs.json")}
    out=[]
    for i, note in enumerate(rec):
        p=pairs[note["iid"]]
        a,b=[grep_run(p["repo"],p[k],note["key"]) for k in ("base","new")]
        parents=[line.split()[1] for line in git(local(p["repo"]),"cat-file","-p",p["new"]).stdout.decode(errors="replace").splitlines() if line.startswith("parent ")]
        out.append({**note,"old_oracle":a,"new_oracle":b,"parent_match":p["base"] in parents,"merge_parents":parents,"old_sha":p["base"],"new_sha":p["new"],"pr":p["pr_url"]})
        if (i+1)%10==0:print("scored",i+1,flush=True)
    save(D/"oracle.json",out)
if __name__=="__main__":{"predict":emit_pred,"score":score}[sys.argv[1]]()

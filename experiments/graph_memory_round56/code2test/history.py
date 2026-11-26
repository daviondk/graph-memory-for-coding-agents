"""Freeze a first-parent history per base SHA, querying raw Git parent objects and tree diffs."""
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import os
from pathlib import Path
import subprocess
import tempfile
from source import HERE,OLD_CACHE,R55,SCRATCH,read,roster,save

ENV={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1"}
def git(repo,*args,stdin=None):
    return subprocess.check_output(["git","-C",str(repo),*args],input=stdin,env=ENV,timeout=180)

def events(repo,base):
    revs=[]
    for depth in (65,150,350):
        git(repo,"fetch","--quiet","--no-tags","--filter=blob:none",f"--depth={depth}","origin",base)
        revs=git(repo,"rev-list","--first-parent","-n","65",base).decode().splitlines()
        if len(revs)==65:break
    assert revs[0]==base and len(revs)>1
    # Supplying the first parent explicitly also handles merge commits.
    from io import BytesIO
    raw=BytesIO(git(repo,"cat-file","--batch",stdin=("\n".join(revs[:-1])+"\n").encode()))
    for commit,parent in zip(revs,revs[1:]):
        name,kind,n=raw.readline().decode().split()
        assert (name,kind)==(commit,"commit")
        body=raw.read(int(n));assert raw.read(1)==b"\n"
        assert next(l.split()[1] for l in body.split(b"\n\n",1)[0].splitlines() if l.startswith(b"parent ")).decode()==parent
    inp="".join(f"{a} {b}\n" for a,b in zip(revs,revs[1:])).encode()
    raw=git(repo,"diff-tree","--stdin","-r","-m","--always","--no-renames","--diff-filter=AMT","--name-only","-z",stdin=inp)
    groups={};markers=set(revs[:-1])
    for v in raw.rstrip(b"\0").split(b"\0"):
        value=v.decode("utf8","surrogateescape")
        if value in markers:
            assert value not in groups
            group=groups[value]=[]
        else:group.append(value)
    assert list(groups)==revs[:-1]
    return {"boundary":revs[-1],"history":[[sha,len(paths),sorted(paths) if 2<=len(paths)<=20 else []] for sha,paths in groups.items()]}

def project(args):
    name,bases=args
    work=SCRATCH/"sources"
    work.mkdir(parents=True,exist_ok=True)
    records={}
    with tempfile.TemporaryDirectory(dir=work,prefix="r56-") as td:
        tmp=Path(td).resolve()
        assert tmp.parent==work.resolve() and tmp.name.startswith("r56-")
        git(tmp,"init","--quiet","--bare")
        git(tmp,"remote","add","origin","https://github.com/"+name+".git")
        git(tmp,"config","remote.origin.promisor","true")
        git(tmp,"config","remote.origin.partialclonefilter","blob:none")
        for base in sorted(bases):
            path=SCRATCH/(base+".json.gz")
            previous=OLD_CACHE/(base+".json.gz")
            if path.exists():r=read(path)
            elif previous.exists():
                r=read(previous);save(path,r)
            else:
                r=dict(repo=name,base=base,**events(tmp,base));save(path,r)
            assert r["repo"]==name and r["base"]==base
            records[base]=r
    print(name,len(records),flush=True)
    return records

def main():
    rows=roster()
    groups=defaultdict(set)
    for r in rows.values():
        if r["eligible"]:groups[r["repo"]].add(r["base"])
    SCRATCH.mkdir(parents=True,exist_ok=True)
    result={}
    with ThreadPoolExecutor(2) as pool:
        for records in pool.map(project,sorted(groups.items())):result.update(records)
    save(HERE/"histories.json.gz",result)
    src=read(R55/"history.json.gz")
    common=set(src)&set(result)
    assert all(result[b]==src[b] for b in common)
    print("snapshots",len(result),"overlap with R55",len(common))
if __name__=="__main__":main()

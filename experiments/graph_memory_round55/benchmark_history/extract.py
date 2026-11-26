"""Acquire commit/path metadata for pinned benchmark base revisions; never check out a PR."""
from collections import defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
R54=HERE.parents[1]/"graph_memory_round54/code_links"
CACHE=Path("D:/CodexResearch/x20-r55-edit-history")
ENV={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1"}

def save(path,obj):
    data=(json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)

def git(path,*args):
    return subprocess.check_output(["git","-C",str(path),*args],env=ENV,timeout=150)

def extract(repo,base,ids):
    checkout=CACHE/repo.replace("/","__")
    if not checkout.exists():
        checkout.mkdir(parents=True)
        git(checkout,"init","--bare","--quiet")
        git(checkout,"remote","add","origin","https://github.com/"+repo+".git")
        git(checkout,"config","remote.origin.promisor","true")
        git(checkout,"config","remote.origin.partialclonefilter","blob:none")
    git(checkout,"fetch","--quiet","--no-tags","--filter=blob:none","--depth=65","origin",base)
    revs=git(checkout,"rev-list","--first-parent","-n","65",base).decode().splitlines()
    if len(revs)<65:
        git(checkout,"fetch","--quiet","--no-tags","--filter=blob:none","--depth=150","origin",base)
        revs=git(checkout,"rev-list","--first-parent","-n","65",base).decode().splitlines()
    assert revs[0]==base and len(revs)>1
    raw=git(checkout,"log","--first-parent","--diff-merges=first-parent","--no-renames",
            "--name-status","-z","--format=%x00@@%H%x00",revs[-1]+".."+base)
    records=[]
    for chunk in re.split(rb"\x00@@(?=[a-f0-9]{40}\x00)",raw)[1:]:
        sha,body=chunk.split(b"\x00",1)
        fields=body.strip(b"\x00").split(b"\x00") if body.strip(b"\x00") else []
        assert len(fields)%2==0
        paths=sorted(p.decode("utf8","surrogateescape") for status,p in zip(fields[::2],fields[1::2])
                     if status.strip()!=b"D")
        assert len(paths)==len(set(paths))
        # A compact path projection suffices for all policies; retain cardinality for excluded giant updates.
        records.append([sha.decode(),len(paths),paths if 2<=len(paths)<=20 else []])
    assert [r[0] for r in records]==revs[:-1]
    return {"repo":repo,"base":base,"boundary":revs[-1],"history":records}

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    rows=json.load(gzip.open(R54/"forecasts.json.gz"))
    groups=defaultdict(list)
    for q,r in rows.items():
        groups[r["repo"],r["commit"]].append(q)
    observations={}
    for (repo,base),ids in sorted(groups.items()):
        fname=CACHE/(base+".json.gz")
        if not fname.exists():
            rec=extract(repo,base,ids)
            save(fname,rec)
        data=json.load(gzip.open(fname))
        assert (data["repo"],data["base"])==(repo,base)
        observations[base]=data
        print(repo,base[:7],len(data["history"]),flush=True)
    save(HERE/"history.json.gz",observations)
    print("pinned",len(observations))

if __name__=="__main__":
    main()

"""Fetch only public commit and tree objects and check every transition with a separate parser."""
import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
R56=EXP/"graph_memory_round56"
sys.path.insert(0,str(R56/"event_intersection"))
from verify_long_git import check

NAMES=("pypa/trove-classifiers","pallets-eco/blinker","lepture/mistune","python-babel/babel","pyparsing/pyparsing","Python-Markdown/markdown")
ENV={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1","GIT_NO_REPLACE_OBJECTS":"1"}

def canonical(obj):
    return (json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()

def save(path,obj):
    data=canonical(obj)
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_bytes(gzip.compress(data,mtime=0) if path.suffix==".gz" else data)
    temp.replace(path)

def load(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())

def git(*args,repo=None):
    cmd=["git"]+(["-C",str(repo)] if repo else [])+list(args)
    return subprocess.check_output(cmd,env=ENV,timeout=160)

def exclusion():
    r55=EXP/"graph_memory_round55"
    files=[r55/"cochange/commits.json.gz",r55/"cochange/continuation/commits.json.gz",
           *sorted((r55/"partner_clock").glob("*pins.json")),
           R56/"event_intersection/long-pins.json",R56/"solver/pins.json"]
    earlier={}
    for f in files:
        data=load(f)
        earlier[str(f.relative_to(EXP)).replace("\\","/")]=sorted(data)
    used={x.casefold() for names in earlier.values() for x in names}
    assert used.isdisjoint(x.casefold() for x in NAMES)
    return earlier

def remote(name):
    url=f"https://github.com/{name}.git"
    ref=git("ls-remote","--symref",url,"HEAD").decode().splitlines()
    head=ref[-1].split()[0]
    assert re.fullmatch("[0-9a-f]{40}",head)
    branch=ref[0].split()[1]
    assert branch.startswith("refs/heads/")
    return dict(head=head,branch=branch,url=url)

def snapshot(name,pin,folder):
    head=pin["head"];repo=Path(folder)/"repo"
    git("init","--bare","--quiet",str(repo))
    git("remote","add","origin",pin["url"],repo=repo)
    git("config","remote.origin.promisor","true",repo=repo)
    git("config","remote.origin.partialclonefilter","blob:none",repo=repo)
    git("-c","protocol.version=2","fetch","--quiet","--no-tags","--depth=1025","--filter=blob:none","origin",head,repo=repo)
    for _ in range(8):
        chain=git("rev-list","--first-parent","-n","1025",head,repo=repo).decode().splitlines()
        size=sum(f.stat().st_size for f in repo.rglob("*") if f.is_file())
        assert size <= 100*1024**2, "temporary repository size exceeds budget"
        if len(chain)==1025:break
        if not git("cat-file","commit",chain[-1],repo=repo).split(b"\n\n",1)[0].count(b"\nparent "):break
        git("fetch","--quiet","--no-tags","--deepen=512","--filter=blob:none","origin",head,repo=repo)
    else:raise RuntimeError("unable to recover 1024 first-parent transitions")
    assert len(chain)>=2 and chain[0]==head
    raw=git("log","--first-parent","--diff-merges=first-parent","--name-only","-z","--no-renames",
            "--format=%x00@@%H%x00",chain[-1]+".."+head,repo=repo)
    rows=[]
    for entry in re.split(rb"\x00@@(?=[0-9a-f]{40}\x00)",raw)[1:]:
        sha,block=entry.split(b"\0",1)
        block=block.removeprefix(b"\0").removeprefix(b"\n")
        paths=sorted(p.decode("utf8","surrogateescape") for p in block.split(b"\0") if p.endswith(b".py"))
        assert len(paths)==len(set(paths))
        rows.append([sha.decode(),paths])
    assert [r[0] for r in rows]==chain[:-1]
    rows.reverse()
    summary=dict(**pin,boundary=chain[-1],transitions=len(rows),large_commits=sum(len(p)>64 for _,p in rows))
    audit=check(repo,summary,rows)
    return rows,summary,audit,size

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--verify-git",action="store_true",help="Refetch pinned heads and repeat the raw-object audit.")
    args=p.parse_args()
    previous=exclusion()
    heads=HERE/"heads.json"
    if not heads.exists():save(heads,{name:remote(name) for name in NAMES})
    pins=load(heads)
    files=[HERE/n for n in ("events.json.gz","pins.json","git-audit.json")]
    data,locks,audits=[load(f) if f.exists() else {} for f in files]
    for name in NAMES:
        if name in data and name in locks and name in audits and not args.verify_git:continue
        with TemporaryDirectory(dir=HERE,prefix="fetch-") as folder:
            rows,lock,audit,size=snapshot(name,pins[name],folder)
        if args.verify_git:
            assert (rows,lock,audit)==(data[name],locks[name],audits[name]["raw_objects"])
        else:
            data[name]=rows;locks[name]=lock;audits[name]=dict(raw_objects=audit,mirror_bytes=size)
            for f,ob in zip(files,(data,locks,audits)):save(f,ob)
        print(name,lock["head"],len(rows),"checked",flush=True)
    save(HERE/"data-seal.json",dict(pins_digest=sha256(canonical(locks)).hexdigest(),
         events_digest=sha256(canonical(data)).hexdigest(),earlier_rosters=previous))
if __name__=="__main__":main()

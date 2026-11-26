"""Fetch only public commit/tree history, then persist a compact path projection."""
import gzip
import json
import os
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
CACHE=Path("D:/CodexResearch/x20-r56-event-history")
NAMES=("networkx/networkx","matplotlib/matplotlib","sphinx-doc/sphinx")
ENV={**os.environ,"GIT_TERMINAL_PROMPT":"0","GIT_LFS_SKIP_SMUDGE":"1"}
def git(repo,*args):
    return subprocess.check_output(["git","-C",str(repo),*args],env=ENV,timeout=300)

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    pins={}
    lock=HERE/"long-pins.json"
    locked=json.loads(lock.read_bytes()) if lock.is_file() else {}
    data={}
    for name in NAMES:
        repo=CACHE/name.replace("/","__")
        if not repo.exists():
            subprocess.run(["git","clone","--bare","--single-branch","--no-tags","--depth=4200",
                            "--filter=blob:none","https://github.com/"+name+".git",str(repo)],
                           env=ENV,timeout=300,check=True)
        head=locked[name]["head"] if locked else git(repo,"rev-parse","HEAD").decode().strip()
        revs=git(repo,"rev-list","--first-parent","-n","4097",head).decode().splitlines()
        for _ in range(6):
            if len(revs)==4097 or git(repo,"rev-parse","--is-shallow-repository").strip()==b"false":break
            git(repo,"fetch","--deepen=1500","--no-tags","origin",head)
            revs=git(repo,"rev-list","--first-parent","-n","4097",head).decode().splitlines()
        raw=git(repo,"log","--first-parent","--diff-merges=first-parent","--no-renames","--name-only","-z",
                "--format=%x00@@%H%x00",revs[-1]+".."+head)
        rows=[];oversize=0
        for entry in re.split(rb"\x00@@(?=[a-f0-9]{40}\x00)",raw)[1:]:
            sha,body=entry.split(b"\x00",1)
            paths=[s.decode("utf8","surrogateescape") for s in body.lstrip(b"\0\n").rstrip(b"\0").split(b"\0") if s.endswith(b".py")]
            assert len(paths)==len(set(paths))
            if len(paths)>64:oversize+=1
            # Preserve all paths in the portable projection; the scorer enforces the filter.
            rows.append([sha.decode(),sorted(paths)])
        assert [r[0] for r in rows]==revs[:-1]
        pins[name]=dict(head=head,boundary=revs[-1],transitions=len(rows),large_commits=oversize)
        data[name]=rows[::-1]
        print(name,len(rows),oversize,flush=True)
    if locked:assert locked==pins
    lock.write_text(json.dumps(pins,sort_keys=True,indent=2)+"\n",encoding="utf8",newline="\n")
    dest=HERE/"long-events.json.gz"
    payload=gzip.compress((json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode(),mtime=0)
    if dest.exists():assert gzip.decompress(dest.read_bytes())==gzip.decompress(payload)
    else:dest.write_bytes(payload)
if __name__=="__main__":main()

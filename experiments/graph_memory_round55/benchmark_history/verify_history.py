"""Verify raw parent links, independent tree diffs, and code-catalog path membership."""
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tarfile
from expand import ARC
from extract import CACHE,HERE,save

def git(repo,args,stdin):
    return subprocess.check_output(["git","-C",str(repo),*args],input=stdin)

def verify_edges():
    data=json.load(gzip.open(HERE/"history.json.gz"))
    unique=set()
    for base,r in data.items():
        history=r["history"]
        repo=CACHE/r["repo"].replace("/","__")
        revs=[h[0] for h in history]+[r["boundary"]]
        assert len(revs)==65 and revs[0]==base
        stream=git(repo,["cat-file","--batch"],("\n".join(revs[:-1])+"\n").encode())
        from io import BytesIO
        raw=BytesIO(stream)
        for sha,parent in zip(revs,revs[1:]):
            name,typ,size=raw.readline().decode().split()
            body=raw.read(int(size))
            assert name==sha and typ=="commit" and raw.read(1)==b"\n"
            headers=body.split(b"\n\n",1)[0].splitlines()
            first=next(v.split(b" ",1)[1].decode() for v in headers if v.startswith(b"parent "))
            assert first==parent
            unique.add((r["repo"],parent,sha))
        pairs="".join(f"{a} {b}\n" for a,b in zip(revs,revs[1:])).encode()
        out=git(repo,["diff-tree","--stdin","-r","--always","--no-renames","-m","--diff-filter=AMT","--name-only","-z"],pairs)
        markers=set(revs[:-1]);group={};current=None
        for term in out.rstrip(b"\0").split(b"\0"):
            token=term.decode("utf-8","surrogateescape")
            if token in markers:
                assert token not in group
                current=token;group[current]=[]
            else:group[current].append(token)
        for sha,m,paths in history:
            actual=sorted(group[sha])
            assert len(actual)==m and (actual if 2<=m<=20 else [])==paths,(r["repo"],sha)
    return sum(len(r["history"]) for r in data.values()),len(unique)

def verify_catalog():
    ranks=json.load(gzip.open(HERE/"expanded-ranks.json.gz"))
    by_base={}
    with tarfile.open(ARC,"r|zst") as archive:
        for member in archive:
            if member.name.startswith("./corpus/") and member.name.endswith(".chunks.jsonl"):
                base=member.name.rsplit("/",1)[1].split(".")[0]
                if base in {r["base"] for r in ranks.values()}:
                    by_base[base]={json.loads(line)["path"] for line in archive.extractfile(member)}
    for r in ranks.values():
        catalog=by_base[r["base"]]
        assert len(catalog)==r["available"]
        assert set(r["shortlist"])<=catalog
        assert not set(p[0] for p in r["evidence"])-catalog
        assert all(set(lst)<=catalog and len(set(lst))==len(lst)==5 for lst in r["ranked"].values())
    return sum(map(len,by_base.values()))

if __name__=="__main__":
    transitions,unique=verify_edges()
    paths=verify_catalog()
    result=dict(parent_pairs_checked=transitions,distinct_parent_pairs=unique,
                snapshot_paths_checked=paths,snapshots=42,tasks=54)
    save(HERE/"independent-history-audit.json",result)
    print(result)

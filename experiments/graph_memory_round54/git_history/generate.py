"""Recover complete import graphs independently at every pinned Git tree, emit signed differences."""
import argparse
import ast
from collections import Counter
from contextlib import contextmanager
import gzip
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import warnings
from inventory import HERE,MIRRORS,git,sha


def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()+b"\n"

def save(file,value,verify=False):
    target=HERE/file
    data=encode(value)
    if target.suffix==".gz":data=gzip.compress(data,mtime=0)
    if verify:
        assert target.read_bytes()==data,file
    else:target.write_bytes(data)

def read(file):
    data=(HERE/file).read_bytes()
    return json.loads(gzip.decompress(data) if file.endswith(".gz") else data)

def mod(path):
    parts=path.removesuffix(".py").split("/")
    if parts[0]=="src":parts=parts[1:]
    package=bool(parts and parts[-1]=="__init__")
    if package:parts=parts[:-1]
    if not all(x.isidentifier() for x in parts):return (),()
    return tuple(parts),tuple(parts if package else parts[:-1])

def parse(source):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree=ast.parse(source)
    except (SyntaxError,ValueError,UnicodeError):
        return None
    out=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for name in node.names:out.append(("abs",0,name.name,()))
        elif isinstance(node,ast.ImportFrom):
            out.append(("from",node.level,node.module or "",tuple(name.name for name in node.names)))
    return out

def targets(specs,package,available):
    out=set()
    for typ,level,module,names in specs or ():
        base=tuple(module.split(".")) if module else ()
        if typ=="abs":
            if base in available:out.add(available[base])
            continue
        if level:
            if level>len(package):continue
            base=package[:len(package)+1-level]+base
        for name in names:
            dest=available.get(base+(name,)) or available.get(base)
            if dest:out.add(dest)
    return out

@contextmanager
def objects(repo):
    proc=subprocess.Popen(["git","-C",str(repo),"cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def get(oid):
        proc.stdin.write(oid.encode()+b"\n");proc.stdin.flush()
        oid2,typ,length=proc.stdout.readline().split();assert typ==b"blob" and oid2.decode()==oid
        blob=proc.stdout.read(int(length));assert proc.stdout.read(1)==b"\n" and len(blob)==int(length)
        return blob
    try:yield get
    finally:
        proc.stdin.close();proc.wait(timeout=8);proc.stdout.close();assert proc.returncode==0

def snapshot(repo,rev):
    out={}
    for line in git(repo,"ls-tree","-rz",rev).split(b"\0"):
        if not line:continue
        meta,path=line.split(b"\t",1);mode,kind,oid=meta.split()
        if mode in (b"100644",b"100755") and path.endswith(b".py"):
            assert kind==b"blob";out[path.decode("utf8")]=oid.decode()
    return out

def sampler(name,repo,revs):
    work=[];dictionary={};oracle=[];meta=[]
    cache={};sizes={};prev_edges=set();old_files={}
    with objects(repo) as get:
        for t,rev in enumerate(revs,1):
            files=snapshot(repo,rev);names=sorted(files)
            born=[]
            for p in names:
                if p not in dictionary:
                    cid=len(dictionary)+1;dictionary[p]=cid;born.append(cid)
            module={p:mod(p) for p in names}
            available={}
            for p in sorted(names,key=lambda p:(not p.startswith("src/"),p)):
                if module[p][0]:available.setdefault(module[p][0],p)
            new_blobs=byte_count=0
            for oid in sorted(set(files.values())-cache.keys()):
                data=get(oid);sizes[oid]=len(data);cache[oid]=parse(data)
                new_blobs+=1;byte_count+=len(data)
            imports={}
            for p,oid in files.items():
                imports[p]=targets(cache[oid],module[p][1],available)-{p}
            degree=Counter(target for items in imports.values() for target in items)
            ranking=sorted(((cid,degree[p]) for p,cid in dictionary.items()),key=lambda v:(-v[1],v[0]))
            edges={(dictionary[target],dictionary[importer]) for importer,x in imports.items() for target in x}
            delta=sorted([[a,b,1] for a,b in edges-prev_edges]+[[a,b,-1] for a,b in prev_edges-edges])
            row=dict(t=t,born=born,delta=delta,sha=rev)
            renames=0
            if t>1 and old_files.keys()-files.keys() and files.keys()-old_files.keys():
                parts=git(repo,"diff-tree","-r","--no-commit-id","--name-status","-z","-M50%","--diff-filter=R",revs[t-2],rev).split(b"\0")
                for i in range(0,len(parts)-1,3):
                    assert parts[i].startswith(b"R")
                    renames+=parts[i+1].endswith(b".py") and parts[i+2].endswith(b".py")
            detail=dict(files=len(files),edges=len(edges),parse_errors=sum(cache[o] is None for o in files.values()),
                born=len(born),missing_paths=len(old_files.keys()-files.keys()),added_paths=len(files.keys()-old_files.keys()),
                renames_py=renames,added_edges=len(edges-prev_edges),removed_edges=len(prev_edges-edges),
                unseen_blobs=new_blobs,bytes_parsed=byte_count)
            oracle.append(dict(top8=ranking[:8],all_scores_sha=sha256(encode(ranking)).hexdigest(),
                    active_edges_sha=sha256(encode(sorted(edges))).hexdigest()))
            work.append(row);meta.append(detail)
            prev_edges=edges;old_files=files
    return work,oracle,meta,dictionary

def main(verify,supplied=None):
    registered=read("registration.json")
    assert all(sha(HERE/k)==v for k,v in registered["files"].items())
    streams={};refs={};metadata={};paths={}
    for name,rec in registered["projects"].items():
        repo=Path(supplied[name]) if supplied else MIRRORS[name]
        streams[name],refs[name],metadata[name],paths[name]=sampler(name,repo,rec["commits"])
        print(name,len(streams[name]),flush=True)
    save("streams.json.gz",streams,verify);save("snapshot-oracle.json.gz",refs,verify)
    save("graph-counts.json.gz",metadata,verify);save("path-ids.json.gz",paths,verify)
    frozen=["registration.json","generate.py","streams.json.gz","snapshot-oracle.json.gz","graph-counts.json.gz","path-ids.json.gz"]
    save("stream-seal.json",{k:sha(HERE/k) for k in frozen},verify)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify",action="store_true");parser.add_argument("--mirror-map",type=Path)
    args=parser.parse_args();main(args.verify,json.loads(args.mirror_map.read_bytes()) if args.mirror_map else None)

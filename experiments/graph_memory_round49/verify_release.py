"""Verify the package without executing included studies. Optional read-only Git object comparison."""
import argparse
import gzip
from hashlib import sha1,sha256
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import subprocess
from tempfile import TemporaryDirectory
import zipfile

OUTER="MANIFEST_SHA256.json"
INDEX="FILE_TYPES.json"
RELEASE="release.json"
ROOT_TOOLS={"verify_release.py","check_studies.py","REPRODUCE_RELEASE_RU.md"}
HASH=re.compile("[0-9a-f]{64}\\Z")
def need(value,message):
    if not value:raise ValueError(str(message))
def digest(data):return sha256(data).hexdigest()
def file_hash(path):
    h=sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def canon(value):return (json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
def parse(raw):
    def object_(pairs):
        d={}
        for k,v in pairs:
            need(k not in d,"duplicate JSON key: "+k);d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=object_)
def valid(name):
    if not isinstance(name,str) or not name:return False
    p=PurePosixPath(name)
    badchar=set('<>:"\\|?*')
    return (p.parts and p.as_posix()==name and not p.is_absolute() and
            all(part not in (".","..",".git") and not part.endswith(("."," ")) and not
                re.fullmatch(r"(?i)(CON|NUL|PRN|AUX|COM[1-9]|LPT[1-9])(?:\..*)?",part) for part in p.parts) and
            all(ord(c)>=32 and c not in badchar for c in name))
def names_ok(names):
    names=list(names);need(all(valid(x) for x in names),"invalid package path")
    need(len(names)==len({x.casefold() for x in names}),"duplicate or case-colliding package path")
    folds={x.casefold() for x in names}
    for name in names:
        need(all(str(p).casefold() not in folds for p in PurePosixPath(name).parents),"file/directory collision")
def entry_info(name,data):
    header=b"blob "+str(len(data)).encode()+b"\0"
    result=dict(bytes=len(data),sha256=digest(data),git_blob_sha1=sha1(header+data).hexdigest(),
                git_blob_sha256=sha256(header+data).hexdigest(),extension="".join(PurePosixPath(name).suffixes[-2:]) if name.endswith(".gz") else PurePosixPath(name).suffix)
    if name.lower().endswith(".f64.gz"):
        logical=gzip.decompress(data);need(len(logical)%8==0,"invalid binary64 array length: "+name)
        result.update(format="gzip-compressed little-endian IEEE 754 binary64 array",elements=len(logical)//8,
                      expanded_bytes=len(logical),expanded_sha256=digest(logical))
    return result
def child_entries(raw):
    m=parse(raw);files=m.get("files",m);need(isinstance(files,dict) and files,"missing child files")
    result={n:v if isinstance(v,str) else v["sha256"] for n,v in files.items()}
    names_ok(result);need(all(HASH.fullmatch(v) for v in result.values()),"invalid child SHA")
    need("manifest.json" not in result and "REPORT_RU.md" in result,"invalid child manifest members")
    return result
def validate_release(r):
    need(r["format"]=="x20-study-release-v1" and r["round"]==49,"format")
    need(r["status"] in ("preview","final"),"status")
    plan=r["requested"];studies=r["studies"];pending=r["pending"]
    need(len(plan)==len(set(plan)) and set(plan)==set(studies)|set(pending) and not(set(studies)&set(pending)),"study register")
    need(all(re.fullmatch(r"[a-z][a-z0-9_]*",s) for s in plan),"study names")
    need(set(r["tools"])==ROOT_TOOLS and studies,"root entries")
    need(all(HASH.fullmatch(v) for v in [*studies.values(),*r["tools"].values(),r["report_sha256"],r["prior_art_sha256"]]),"invalid digest")
    if r["status"]=="final":need(not pending,"unfinished final release")
def validate(names,read):
    names_ok(names)
    outer=parse(read(OUTER));release=parse(read(RELEASE));validate_release(release)
    expected={"REPORT_RU.md":release["report_sha256"],"PRIOR_ART_RU.md":release["prior_art_sha256"],
              **release["tools"],RELEASE:digest(read(RELEASE))}
    for s,seal in release["studies"].items():
        member=s+"/manifest.json";buf=read(member);need(digest(buf)==seal,member);expected[member]=seal
        for local,h in child_entries(buf).items():expected[s+"/"+local]=h
    index=parse(read(INDEX));need(set(index)==set(expected),"inventory membership")
    for name,h in expected.items():
        raw=read(name);info=entry_info(name,raw)
        need(info==index[name] and info["sha256"]==h,name)
    expected[INDEX]=digest(read(INDEX))
    need(outer==expected,"outer SHA256 values");need(set(names)==set(expected)|{OUTER},"unexpected or missing members")
    return release,outer
def archive(path,want=None):
    if want:need(file_hash(path)==want,"outer ZIP SHA256 mismatch")
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            mode=i.external_attr>>16
            need(not i.is_dir() and not stat.S_ISLNK(mode) and not i.flag_bits&1,"unsupported entry: "+i.filename)
        return validate(z.namelist(),z.read)
def directory(path):
    files=[]
    for f in path.rglob("*"):
        need(not f.is_symlink(),"symlink")
        if f.is_file():files.append(f.relative_to(path).as_posix())
    return validate(files,lambda n:(path/n).read_bytes())
def store_zip(path,files):
    """Use fixed member order, bytes, timestamp, mode and no compression-version dependency."""
    need(not path.exists(),"output already exists")
    path.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as scratch:
        tmp=Path(scratch)/"package.zip"
        with zipfile.ZipFile(tmp,"x",allowZip64=True) as z:
            for name in sorted(files):
                val=files[name];raw=val.read_bytes() if isinstance(val,Path) else val
                info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16
                z.writestr(info,raw,compress_type=zipfile.ZIP_STORED)
        archive(tmp);os.link(tmp,path)
def repack(directory_path,path):
    root=directory_path.resolve()
    need(not path.resolve().is_relative_to(root),"output must be outside the imported tree")
    _,files=directory(root);store_zip(path,{n:root/n for n in [*files,OUTER]})
def import_new(zip_path,dest,want):
    need(HASH.fullmatch(want),"supply pinned SHA256")
    _,files=archive(zip_path,want);need(not dest.exists() and dest.parent.is_dir(),"import path must be new")
    with TemporaryDirectory(dir=dest.parent) as scratch:
        stage=Path(scratch)/"stage";stage.mkdir()
        with zipfile.ZipFile(zip_path) as z:
            for n in [*files,OUTER]:
                f=stage/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(z.read(n))
        directory(stage);os.rename(stage,dest)
def verify_git(directory_path,repo,ref,prefix):
    _,files=directory(directory_path);names=set(files)|{OUTER}
    need(valid(prefix),"Git relative directory prefix")
    def git(*args,data=None):
        return subprocess.run(["git","-C",str(repo),*args],input=data,stdout=subprocess.PIPE,check=True).stdout
    commit=git("rev-parse","--verify","--end-of-options",ref+"^{commit}").decode().strip()
    algorithm=git("rev-parse","--show-object-format").decode().strip()
    need(algorithm in ("sha1","sha256"),"Git object format")
    listing=git("ls-tree","-z","-r",commit+":"+prefix).split(b"\0");objects={}
    for row in listing:
        if not row:continue
        tags,name=row.split(b"\t",1);mode,typ,oid=tags.split()
        need(mode in (b"100644",b"100755") and typ==b"blob",name);objects[name.decode()]=oid.decode()
    need(set(objects)==names,"Git subtree differs from bundle")
    for name,oid in objects.items():
        data=git("cat-file","blob",oid)
        need(entry_info(name,data)["git_blob_"+algorithm]==oid and data==(directory_path/name).read_bytes(),name)
    return len(objects)
def main():
    cli=argparse.ArgumentParser();choice=cli.add_subparsers(dest="op",required=True)
    p=choice.add_parser("zip");p.add_argument("path",type=Path);p.add_argument("--sha256")
    p=choice.add_parser("tree");p.add_argument("path",type=Path,nargs="?",default=Path(__file__).resolve().parent)
    p=choice.add_parser("import");p.add_argument("path",type=Path);p.add_argument("destination",type=Path);p.add_argument("--sha256",required=True)
    p=choice.add_parser("repack");p.add_argument("path",type=Path);p.add_argument("output",type=Path)
    p=choice.add_parser("git");p.add_argument("path",type=Path);p.add_argument("--repo",type=Path,required=True);p.add_argument("--ref",required=True);p.add_argument("--prefix",required=True)
    a=cli.parse_args()
    if a.op=="import":import_new(a.path,a.destination,a.sha256);print("Verified import",a.destination);return
    if a.op=="repack":repack(a.path,a.output);print(file_hash(a.output));return
    if a.op=="git":print("Verified archived Git blobs",verify_git(a.path,a.repo,a.ref,a.prefix));return
    release,files=archive(a.path,a.sha256) if a.op=="zip" else directory(a.path)
    print(release["status"],len(release["studies"]),"studies",len(files)+1,"verified files")
if __name__=="__main__":main()

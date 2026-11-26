"""Verify released bytes and scores, optionally checking their Git objects and running the studies."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
PINNED={
    "baseline/manifest.json":"7eaf3cabb047efc0128f97b4284ec0eddee120b7f5d615eda76f182e7c64a5ae",
    "code/manifest.json":"f7c4a016f4d6a946fdb84df0baed0857c462fe4abd66a475d837bc54554be637",
    "transfer/SHA256.json":"f9012fbbd9d29c8db214e5e80ac56338f99f1c06ae66fc0062d84fc29c63e449",
    "routing/SHA256.json":"5f9bae02d47e992556b273ca6c51e36408bbf40bd70d147356eb776d379e52e4",
    "frozen_ablation/manifest.json":"34b2fedd9a11e61fb019281d1ee0465b3ca9c14a0cf5d283d5f5570eecf1b691",
    "edge_placebo/manifest.json":"a2c7d158dca6ca5ee19da35c669f7edf246e45bea9f720564a2b1a7dc82abc6d",
}

def h(data):
    return sha256(data).hexdigest()

def check(files):
    for n,v in files.items():
        if h((ROOT/n).read_bytes())!=v:
            raise ValueError("Digest mismatch: "+n)

def tree():
    index=ROOT/"manifest.json"
    inv=json.loads(index.read_bytes())["files"]
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and p!=index}
    assert actual==set(inv),(actual-set(inv),set(inv)-actual)
    check(inv);check(PINNED)
    for n in PINNED:
        path=ROOT/n
        source=json.loads(path.read_bytes())
        files=source.get("files",source)
        for name,digest in files.items():
            assert h((path.parent/name).read_bytes())==digest,(n,name)
    return dict(inv,**{"manifest.json":h(index.read_bytes())})

def git(ref,expected):
    repo=ROOT.parents[1]
    prefix=ROOT.relative_to(repo).as_posix()+"/"
    raw=subprocess.check_output(["git","ls-tree","-rz",ref,"--",prefix],cwd=repo)
    entries={}
    for line in raw.split(b"\0"):
        if not line:continue
        meta,name=line.split(b"\t",1)
        t,kind,oid=meta.decode().split()
        assert kind=="blob" and t in ("100644","100755")
        entries[name.decode()[len(prefix):]]=oid
    assert set(entries)==set(expected),(set(entries)-set(expected),set(expected)-set(entries))
    proc=subprocess.Popen(["git","cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,cwd=repo)
    try:
        for name,oid in entries.items():
            proc.stdin.write(oid.encode()+b"\n");proc.stdin.flush()
            got,kind,n=proc.stdout.readline().split()
            assert got.decode()==oid and kind==b"blob"
            assert h(proc.stdout.read(int(n)))==expected[name],name
            assert proc.stdout.read(1)==b"\n"
    finally:
        proc.stdin.close();proc.stdout.close();assert proc.wait()==0
    print(f"Checked {len(entries)} archived Git blobs at {ref}.")

def studies(science,system):
    commands=[("transfer",science,["verify.py","--manifest"]),("routing",science,["verify.py","--manifest"]),
              ("baseline",science,["verify_all.py"]),("code",system,["verify.py","--source"]),
              ("edge_placebo",science,["verify.py","--source"]),("frozen_ablation",science,["verify_ablation.py"]),
              ("policy_replay",science,["verify.py"]),("policy_replay",science,["edge_audit.py"]),
              ("policy_replay",science,["verify_views.py"]),("submission",system,["verify.py"])]
    for sub,exe,args in commands:
        subprocess.run([exe,"-B","-X","utf8",*args],cwd=ROOT/sub,check=True,
                       env=dict(os.environ,OPENBLAS_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1"))

if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument("--git-ref");arg.add_argument("--studies",action="store_true")
    arg.add_argument("--science-python",default=sys.executable);arg.add_argument("--system-python",default=sys.executable)
    opt=arg.parse_args();entries=tree()
    if opt.git_ref:git(opt.git_ref,entries)
    if opt.studies:
        studies(opt.science_python,opt.system_python);assert entries==tree()
    print(f"Verified {len(entries)} files and {len(PINNED)} independent input manifests.")


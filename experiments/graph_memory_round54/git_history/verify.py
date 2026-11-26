"""Validate local artifacts and independently exercise parsing conventions with fixed examples."""
import argparse
import json
import sqlite3
import subprocess
import sys
from generate import HERE,mod,parse,read,sha,targets

def ast_checks():
    files=["src/pkg/__init__.py","src/pkg/util.py","src/pkg/sub/__init__.py","src/pkg/sub/a.py"]
    mods={mod(p)[0]:p for p in files}
    assert mod(files[-1])==(tuple(["pkg","sub","a"]),tuple(["pkg","sub"]))
    named=targets(parse(b"from .. import util\nfrom .a import Symbol\nimport outside\n"),("pkg","sub"),mods)
    assert named==set([files[1],files[3]])
    assert targets(parse(b"from ... import util\n"),("pkg","sub"),mods)==set()
    assert targets(parse(b"from pkg import absent\n"),(),mods)=={files[0]}
    assert parse(b"def broken(\n") is None
    changed=mods.copy();del changed[("pkg","util")]
    assert targets(parse(b"from .. import util\n"),("pkg","sub"),changed)=={files[0]}

def main(args):
    ast_checks()
    logs={}
    if args.git:
        cmd=[sys.executable,"-B","-X","utf8","generate.py","--verify"]
        if args.mirror_map:cmd+=["--mirror-map",args.mirror_map]
        logs["git"]=subprocess.check_output(cmd,cwd=HERE,text=True,encoding="utf-8").splitlines()
    for script in ("replay","extension"):
        logs[script]=subprocess.check_output([sys.executable,"-B","-X","utf8",script+".py","--verify"],cwd=HERE,text=True,encoding="utf-8").splitlines()
    data=read("streams.json.gz");refs=read("snapshot-oracle.json.gz")
    reg=read("registration.json")
    for q,rs in data.items():
        assert len(rs)==len(refs[q])==120 and [r["sha"] for r in rs]==reg["projects"][q]["commits"]
    proofs=["registration.json","stream-seal.json","policy-seal.json","extension-seal.json","results.json",
            "extension-results.json","event-costs.json.gz","extension-costs.json.gz","verify.py"]
    out=dict(projects=len(data),versions=sum(map(len,data.values())),operational_transitions=sum(len(r)-1 for r in data.values()),
             policies=8,schedules=2,python=sys.version.split()[0],sqlite=sqlite3.sqlite_version,
             hashes={p:sha(HERE/p) for p in proofs},stdout=logs)
    if args.log:
        from generate import save
        save("verification.json",out)
    print("PASS",out["projects"],out["versions"],out["policies"],out["schedules"])

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--git",action="store_true");ap.add_argument("--log",action="store_true")
    ap.add_argument("--mirror-map");main(ap.parse_args())

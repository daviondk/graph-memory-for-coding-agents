"""Restore Sphinx base archives or recompute Sphinx old-line labels from official inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent
LOC=ROOT/"localization"
def read(p):
    return json.loads(p.read_bytes())
def file_sha(path):
    h=hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda:src.read(2**20),b""):h.update(block)
    return h.hexdigest()
def restore(base,ids):
    for task in ids:
        d=base/"inputs"/task
        rec=read(d/"source.json")
        assert re.fullmatch(r"https://codeload\.github\.com/sphinx-doc/sphinx/tar\.gz/[0-9a-f]{40}",rec["url"])
        path=d/"base.tar.gz"
        if path.exists():
            if file_sha(path)!=rec["sha256"]:raise ValueError("Existing archive has unexpected bytes: "+task)
            continue
        tmp=d/"base.tar.gz.partial"
        req=urllib.request.Request(rec["url"],headers={"User-Agent":"research-artifacts-reproduction"})
        with urllib.request.urlopen(req,timeout=90) as src,tmp.open("wb") as out:shutil.copyfileobj(src,out)
        if file_sha(tmp)!=rec["sha256"]:raise ValueError("Archive digest mismatch: "+task)
        tmp.replace(path)
def check(dbfile):
    import duckdb
    sys.path.insert(0,str(LOC))
    import evaluate
    proof=read(ROOT/"primary_input_parity.json")
    assert file_sha(dbfile) in {proof["sha256_official_file"],proof["sha256_original_file"]}
    fields=proof["fields"]
    db=duckdb.connect()
    records={}
    roster={x["task"] for x in read(ROOT/"third_party_notices/sources.json")}
    for row in db.execute("select "+",".join(fields)+" from read_parquet(?)",[str(dbfile)]).fetchall():
        r=dict(zip(fields,row))
        if r["instance_id"] not in roster:continue
        for k in ("FAIL_TO_PASS","PASS_TO_PASS"):
            if isinstance(r[k],str):r[k]=json.loads(r[k])
        records[r["instance_id"]]=r
    packed=json.dumps(records,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()
    assert hashlib.sha256(packed).hexdigest()==proof["official_projection_sha256"]
    count=0
    for phase in (LOC,LOC/"frontier"):
        evaluate.D=phase
        for row in read(phase/"scores_per_issue.json"):
            t=row["id"]
            if not t.startswith("sphinx-doc__"):continue
            full,skipped=evaluate.external_sites(t,records[t]["patch"])
            assert full==set(map(tuple,row["sites"])),t
            count+=1
    print("All",count,"Sphinx issues reproduce identical old-line targets.")
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("restore","grade"))
    parser.add_argument("--parquet",type=Path)
    args=parser.parse_args()
    if args.action=="restore":
        for base in (LOC,LOC/"frontier"):
            restore(base,read(base/"cohort_sphinx.json")["ids"])
    elif args.parquet:check(args.parquet)
    else:parser.error("grade requires --parquet")
if __name__=="__main__":main()

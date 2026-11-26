"""Verify the recorded inputs, primary measurements, reports and the offline package."""
from hashlib import sha256
from pathlib import Path
import argparse
import gzip
import json
import re
from zipfile import ZipFile

D=Path(__file__).resolve().parent
LEDGER=D/"artifact-digests.json"
def load(path):
    buf=(D/path).read_bytes()
    return json.loads(gzip.decompress(buf) if str(path).endswith(".gz") else buf)
def digest(file):
    return sha256(file.read_bytes()).hexdigest()
def inventory():
    files={}
    for f in sorted(D.rglob("*")):
        if not f.is_file() or f==LEDGER:continue
        key=f.relative_to(D)
        if "__pycache__" in key.parts or any(p.startswith("tmp") for p in key.parts):continue
        if f.suffix in (".pyc",".pyo") or f.name.endswith(("-shm","-wal")):continue
        files[key.as_posix()]=digest(f)
    return files
def verify():
    labels=load("next_read/labels.json.gz")
    reads=load("next_read/explicit-decisions.json.gz")
    assert len(labels)==len(reads)==283 and set(labels)==set(reads)
    assert len({v["repo"] for v in reads.values()})==25
    totals={}
    for name in ("memory","fusion","embed4"):
        totals[name]=sum(row["chosen"][name] in labels[q] for q,row in reads.items())
    assert totals=={"memory":20,"fusion":16,"embed4":26}
    snapshots=load("cutoff/correctness.json")["packets"]
    assert {k:v["counts"]["index"] for k,v in snapshots.items()}=={"index":1072,"unchanged":533,"boundary":39}
    assert len({v["packet_hash"] for v in snapshots.values()})==1
    reserve=load("reserve/partial-results.json")["plans"]
    classic=load("reserve/classic-results.json")["plans"]
    for k in ("8","12"):
        v=reserve["partial-"+k];b=classic["classic-"+k]
        assert (v["warm_probes"], v["warm_rows"], b["warm_probes"], b["warm_rows"])==(
            (36,38,39,41) if k=="8" else (0,0,0,0))
    external=load("git_history/extension-results.json")["schedules"]["once"]
    assert [(external[p]["steady"]["warm_probes"], external[p]["steady"]["cold_rows"])
            for p in ("partial8","classic8","partial12")]==[(0,48),(1,48),(0,72)]
    caps=load("execution/cap-results.json")["summaries"]
    assert set(x["passed"] for x in caps.values())=={43}
    scores=load("learned_read/results.json")["all"]["summary"]
    assert [scores[k]["new_hits"] for k in ("memory8","static7","rrf7")]==[23,22,24]
    artifact=load("submission/verification.json")
    assert digest(D/"submission/candidate.zip")==artifact["sha256"]
    with ZipFile(D/"submission/candidate.zip") as z:
        ledger=json.loads(z.read("CONTENT_SHA256.json"))
        assert len(ledger)+1==len(z.namelist())
        assert all(sha256(z.read(k)).hexdigest()==v for k,v in ledger.items())
        assert z.read("paper.pdf")== (D/"submission/paper.pdf").read_bytes()
        assert artifact["pages"]==4 and artifact["seconds"]<=300 and artifact["video_bytes"]<=50_000_000
        assert z.read("tox-replay.html")==(D/"case_replay/index.html").read_bytes()
    for f in [D/"REPORT_RU.md",D/"LITERATURE_RU.md",D/"cutoff/REPORT_RU.md",D/"next_read/REPORT_RU.md"]:
        for path in re.findall(r"\[[^\]]+\]\(([^)]+)\)",f.read_text(encoding="utf8")):
            assert path.startswith(("https://","http://","#")) or (f.parent / path).exists(), (f,path)
    return totals
if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--record",action="store_true")
    opts=cli.parse_args()
    totals=verify()
    current=inventory()
    if opts.record:
        LEDGER.write_text(json.dumps(current,indent=2,sort_keys=True)+"\n",encoding="utf8")
    else:assert json.loads(LEDGER.read_bytes())==current
    print("Verified",len(current),"files and additional-source hits",totals)

"""Read-only verification of frozen evidence (Python 3.8+, standard library)."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json

ROOT = Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def hits(sites, spans):
    return sum(any(p==f and a<=n<=b for f,a,b in spans) for p,n in sites)

def verify_localization(base,frontier=False):
    lock=read(base/"predictions.lock.json")
    rows={r["id"]:r for r in read(base/"scores_per_issue.json")}
    assert rows.keys()==lock["predictions"].keys()
    for task,expected in lock["predictions"].items():
        p=base/"predictions"/(task+".json.gz")
        assert sha(p)==expected
        rec=read(p);row=rows[task];sites=row["sites"]
        for arm,a in rec["arms"].items():
            reported=row["arms"][arm]
            count=hits(sites,a["kept"])
            assert count==reported["lines_in_packet" if frontier else "cover"]
            assert int(count>0)==reported["packet" if frontier else "hit"]
            assert a["tokens"]==reported["tokens"]<=1800
            if frontier:
                assert len(a["paths"])<=8
                assert sum(p in a["paths"] for p,n in sites)==reported["lines_in_files"]
    return len(rows)

def verify_reader(round6):
    d=ROOT/"reader";inputs=read(d/"input_lock.json");answers=read(d/"answer_lock.json")
    prefix="../../graph_memory_round6/"
    for name,h in inputs["files"].items():
        path=round6/name[len(prefix):] if name.startswith(prefix) else d/name
        assert sha(path)==h,name
    assert answers["input"]==sha(d/"input_lock.json")
    reqs=read(d/"requests.json.gz")
    for filename,h in answers["calls"].items():
        p=d/"calls"/filename
        assert sha(p)==h
        c=read(p);key=filename.partition(".")[0]
        assert c["request"]==reqs[key]
        encoded=json.dumps(c["request"],ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
        assert hashlib.sha256(encoded).hexdigest()==key
    rows=read(d/"rows.json");totals=read(d/"results.json")["totals"]
    for arm,row in totals.items():
        for key,num in row.items():assert sum(x["arms"][arm][key] for x in rows)==num
    return len(rows),len(reqs)

def main():
    loc=ROOT/"localization";a=verify_localization(loc);b=verify_localization(loc/"frontier",True)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round6",type=Path,default=ROOT.parent/"graph_memory_round6")
    c,d=verify_reader(parser.parse_args().round6)
    online=ROOT/"online"
    for p in (online,online/"search",online/"search/followup"):
        lock=read(p/"predictions_lock.json")
        if "files" in lock:
            for n,h in lock["files"].items():assert sha(p/n)==h
        else:
            assert sha(p/"predictions.jsonl.gz")==lock["sha256"]
            assert sha(p/"freeze.json")==lock["freeze"]
    print(f"Checked {a}+{b} localization tasks, {d} responses for {c} reader tasks, and three online prediction locks.")
if __name__=="__main__":
    main()

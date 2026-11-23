"""Recheck set arithmetic with SQLite and compute the paper's per-project ratio convention."""
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from statistics import mean
import sys

from audit import CODES, METHODS, ROOT

repo = Path(sys.argv[1])
sources = json.loads((ROOT/"sources.json").read_bytes())
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE s(p,k,m,f,PRIMARY KEY(p,k,m,f))")
con.execute("CREATE TABLE base(p,k,m,n,b,PRIMARY KEY(p,k,m))")
for path, record in sources["files"].items():
    raw = (repo/path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != record["sha256"]:
        raw = raw.replace(b"\r\n", b"\n")  # Git for Windows checkout line endings
    assert hashlib.sha256(raw).hexdigest() == record["sha256"], path
    paths = Path(path)
    project = next((p for p, c in CODES.items() if paths.stem.endswith("_"+c)), None)
    if paths.parts[0] == "ground truth":
        method = "gold"
        project = paths.stem.removeprefix("gt_")
    elif "babelrts" in path:
        method = "BabelRTS"
        project = paths.stem.split("_")[1].replace("scikit-learn","sklearn")
    else:
        method = "EkstaP" if "ekstap" in path else "NameRTS"
    assert project in CODES
    for row in json.loads(raw):
        if not row.get("target", True):
            continue
        key = row["current"]
        con.execute("INSERT INTO base VALUES(?,?,?,?,?)",(project,key,method,row.get("total_tests"),row["true_parent"]))
        con.executemany("INSERT INTO s VALUES(?,?,?,?)",[(project,key,method,f) for f in row["tests_to_run"]])
reference = json.loads(gzip.decompress((ROOT/"counts.json.gz").read_bytes()))
by_key = {(r["project"],r["sha"],r["method"]): r for r in reference}
matched = 0
paper = {}
for p,k,m,n,b in con.execute("""SELECT z.p,z.k,z.m,g.n,g.b FROM base z JOIN base g
                    ON z.p=g.p AND z.k=g.k AND z.b=g.b WHERE g.m='gold' AND z.m!='gold'"""):
    row = by_key[p,k,m]
    params = [p,k,m,p,k]
    counts = {}
    for tag, expr in (("hit","INTERSECT"),("extra","EXCEPT")):
        q = "SELECT COUNT(*) FROM (SELECT f FROM s WHERE p=? AND k=? AND m=? "+expr+" SELECT f FROM s WHERE p=? AND k=? AND m='gold')"
        counts[tag] = con.execute(q,params).fetchone()[0]
    g = con.execute("SELECT count(*) FROM s WHERE p=? AND k=? AND m='gold'",(p,k)).fetchone()[0]
    assert (n,b,g,counts["hit"],counts["extra"],g-counts["hit"]) == (row["n"],row["true_parent"],row["gold"],row["hit"],row["extra"],row["missed"])
    matched += 1
assert matched == len(reference) == len(by_key)
for method in METHODS:
    panel = [r for r in reference if r["method"] == method]
    macro = {}
    for project in CODES:
        current = [r for r in panel if r["project"]==project]
        n = sum(r["n"] for r in current)
        macro[project] = 1-sum(r["selected"] for r in current)/n
    paper[method]={"by_project":macro,"mean_project_ratio":mean(macro.values())}
name = [r for r in reference if r["method"] == "NameRTS"]
detail = {}
for p in CODES:
    whole = [r for r in name if r["project"] == p and r["full"]]
    detail[p] = dict(full=len(whole), parents=len({r["true_parent"] for r in whole}),
                     known_affected=sum(r["gold"] for r in whole), n=sum(r["n"] for r in whole))
output = dict(checked_rows=matched, project_ratio_method=paper, full_by_project=detail,
              full_exact=sum(r["full"] and r["exact"] for r in name),
              mean_best_available_reduction=mean(1-r["gold"]/r["n"] for r in name))
(ROOT/"verification.json").write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",encoding="utf8")
print("Independently checked",matched,"triplets across",len(CODES),"projects;",paper["NameRTS"]["mean_project_ratio"])


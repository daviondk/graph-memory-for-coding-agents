"""Build a tiny replay database and answer two-anchor queries from SQL incidence counts."""
from collections import Counter
from contextlib import closing
from fractions import Fraction
from heapq import nlargest
from pathlib import Path
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "anchor_risk"))
from risk import History
from evaluate_risk import read
from ambiguity import triples

CASES = {"gain": ("dask/dask", "06c1bb72be354a1629f6e958376420101fed4258"),
         "loss": ("pydata/xarray", "503b262d42877eb5de6c803d520983e364ebdfab")}
SCHEMA = """
CREATE TABLE example(case_id TEXT PRIMARY KEY, repo TEXT, sha TEXT, a TEXT, b TEXT);
CREATE TABLE file(case_id TEXT, fid INTEGER, path TEXT, freq INTEGER, PRIMARY KEY(case_id,fid)) WITHOUT ROWID;
CREATE TABLE event(case_id TEXT, j INTEGER, sha TEXT, m INTEGER, PRIMARY KEY(case_id,j)) WITHOUT ROWID;
CREATE TABLE participant(case_id TEXT,j INTEGER,fid INTEGER,PRIMARY KEY(case_id,j,fid)) WITHOUT ROWID;
CREATE TABLE annotation(case_id TEXT, path TEXT,PRIMARY KEY(case_id,path)) WITHOUT ROWID;
CREATE TABLE synthetic(shift INTEGER,a INTEGER,b INTEGER,c INTEGER,PRIMARY KEY(shift,a,b)) WITHOUT ROWID;
"""
COUNTS = """
WITH marks AS (
 SELECT e.case_id,e.j,e.m,MAX(p.fid=?) AS has_a,MAX(p.fid=?) AS has_b
 FROM event AS e JOIN participant AS p USING(case_id,j)
 WHERE e.case_id=? GROUP BY e.case_id,e.j,e.m
)
SELECT p.fid,m.m,m.has_a,m.has_b,COUNT(*) FROM marks AS m
JOIN participant AS p USING(case_id,j) WHERE p.fid NOT IN (?,?)
GROUP BY p.fid,m.m,m.has_a,m.has_b
"""


def build(path):
    logs = read(HERE / "new-queries.json.gz")
    data = read(HERE / "events.json.gz")
    with closing(sqlite3.connect(path)) as db:
        db.executescript(SCHEMA)
        for case, (repo, sha) in CASES.items():
            row = next(r for r in logs[repo] if r["sha"] == sha)
            state = History()
            for rev, raw in data[repo][:row["t"]]:
                state.observe(raw if len(raw) <= 64 else [])
            seeds = row["seeds"]
            db.execute("INSERT INTO example VALUES(?,?,?,?,?)", (case,repo,sha,*seeds))
            db.executemany("INSERT INTO file VALUES(?,?,?,?)",
                           ((case,i,p,state.frequency[i]) for p,i in state.ids.items()))
            raw_refs = dict(data[repo][:row["t"]])
            for j, witness in enumerate(row["evidence"]):
                paths = raw_refs[witness]
                db.execute("INSERT INTO event VALUES(?,?,?,?)",(case,j,witness,len(paths)))
                db.executemany("INSERT INTO participant VALUES(?,?,?)",((case,j,state.ids[p]) for p in paths))
            future_sha, future = data[repo][row["t"]]
            assert future_sha == sha
            db.executemany("INSERT INTO annotation VALUES(?,?)", ((case,p) for p in future if p not in seeds))
        db.executemany("INSERT INTO synthetic VALUES(?,?,?,?)",
                       ((s,a,b-16,c-32) for s in range(16) for a,b,c in triples(16,s)))
        db.commit()


def inspect(db, case):
    repo, rev, a, b = db.execute("SELECT repo,sha,a,b FROM example WHERE case_id=?", (case,)).fetchone()
    catalog = list(db.execute("SELECT fid,path,freq FROM file WHERE case_id=?", (case,)))
    ids = {path:i for i,path,_ in catalog}
    paths = {i:path for i,path,_ in catalog}
    recent = {i:freq for i,_,freq in catalog}
    ia, ib = ids.get(a,-1), ids.get(b,-1)
    av,bv,joint = Counter(),Counter(),Counter()
    for f,m,ha,hb,n in db.execute(COUNTS,(ia,ib,case,ia,ib)):
        av[f] += Fraction(ha*n,m-1)
        bv[f] += Fraction(hb*n,m-1)
        if ha and hb and m > 2:
            joint[f] += Fraction(n,m-2)
    base = av + bv
    total = sum(base.values())
    harm = {f: 2*av[f]*bv[f]/base[f] for f in base}
    hsum = sum(harm.values())
    cs = sum(joint.values())
    available = [f for f in paths if f not in (ia,ib)]
    prior = {f: base[f]/total if total else 0 for f in available}
    fields = {"sum": prior, "joint": {f: prior[f]+joint[f] for f in available},
              "placebo": {f: prior[f]+(cs*harm.get(f,0)/hsum if hsum else 0) for f in available}}
    ranks = {k: nlargest(8,available,key=lambda i:(scores[i],base[i],recent[i],-i)) for k,scores in fields.items()}
    witnesses = []
    for j,sha,m in db.execute("SELECT j,sha,m FROM event WHERE case_id=? ORDER BY j",(case,)):
        fs = [paths[i] for (i,) in db.execute("SELECT fid FROM participant WHERE case_id=? AND j=? ORDER BY fid",(case,j))]
        witnesses.append(dict(sha=sha,files=fs,m=m,joint=(a in fs and b in fs)))
    # Gold is accessed only after the immutable ranking is computed.
    gold = sorted(p for p, in db.execute("SELECT path FROM annotation WHERE case_id=?",(case,)))
    return dict(case=case,repo=repo,rev=rev,seeds=[a,b],gold=gold,
                ranks={k:[paths[i] for i in top] for k,top in ranks.items()},witnesses=witnesses)


def world(db, shift, a, b):
    c, = db.execute("SELECT c FROM synthetic WHERE shift=? AND a=? AND b=?", (shift,a,b)).fetchone()
    left = dict(db.execute("SELECT c,COUNT(*) FROM synthetic WHERE shift=? AND a=? GROUP BY c",(shift,a)))
    right = dict(db.execute("SELECT c,COUNT(*) FROM synthetic WHERE shift=? AND b=? GROUP BY c",(shift,b)))
    assert len(left) == len(right) == 16 and all(n == 1 for n in (*left.values(),*right.values()))
    return dict(shift=shift,a=a,b=b,third=c,projection=[left[i]+right[i] for i in range(16)])

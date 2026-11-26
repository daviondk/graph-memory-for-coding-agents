"""Independently check tree pairs, chronological prediction and artifact integrity."""
import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from extract import HERE, R54, read_json, write_json

def diff_check(root, project, source):
    revs = source["revisions"]
    parents = [source["base_parent"], *[row[0] for row in revs[:-1]]]
    query = "".join(f"{rev} {parent}\n" for (rev, _),parent in zip(revs, parents, strict=True))
    mirror = root/project.replace("/", "__")
    args = ["git", "-C", str(mirror), "diff-tree", "--stdin", "-r", "--no-renames", "--name-only",
            "--always", "--format=%x00PAIR%H%x00", "-z", "--", "*.py"]
    raw = subprocess.check_output(args, input=query.encode())
    sections = re.split(rb"\x00PAIR([0-9a-f]{40})\x00", raw)[1:]
    assert len(sections) == len(revs)*2
    for j,(sha,paths) in enumerate(revs):
        assert sections[2*j].decode() == sha
        names = sections[2*j+1].removeprefix(b"\0").removeprefix(b"\n").rstrip(b"\0")
        observed = [] if not names else [s.decode("utf8","surrogateescape") for s in names.split(b"\0")]
        assert sorted(observed)==paths, (project,sha)
    return len(revs)

def paths_at(rows, t):
    return rows[t][1] if len(rows[t][1]) <= 64 else []

def check_conditional(project, rows, benchmark):
    logs = {event[0]:event for event in benchmark}
    prior = []
    ids = {}
    checked = 0
    for t,(sha,_) in enumerate(rows):
        paths = paths_at(rows,t)
        if t >= 64 and len(paths)>=2:
            record = logs.pop(sha)
            m = len(paths)
            selected = paths[int(sha,16)%m]
            assert record[1:3] == [m,selected]
            hist32 = prior[-32:]
            freq = Counter(p for _,ps in hist32 for p in ps)
            degree = Counter()
            for _,ps in hist32:
                for p in ps:
                    degree[p] += len(ps)-1
            totals = [[0]*7 for _ in range(3)]
            for anchor in paths:
                relevant = [entry for entry in prior if anchor in entry[1]]
                proposals = [freq,degree]
                windows = [[e for e in prior[-16:] if anchor in e[1]],
                           [e for e in hist32 if anchor in e[1]], relevant, relevant[-8:],
                           sorted(relevant,key=lambda x:x[0])[:8]]
                for arr in windows:
                    proposals.append(Counter(path for _,ps in arr for path in ps))
                work = [0,0,*map(len,windows)]
                hits = []
                for weights in proposals:
                    best = sorted((p for p in ids if p!=anchor), key=lambda p:(-weights[p],-freq[p],ids[p]))[:8]
                    hits.append(len(set(best) & (set(paths)-{anchor})))
                if anchor == selected:
                    assert [hits,work] == record[3:5], (project,sha)
                for i,h in enumerate(hits):
                    totals[0][i] += h
                    totals[1][i] += int(h>0)
                    totals[2][i] += work[i]
                checked += 1
            assert totals == record[5:], (project,sha)
        prior.append((sha, frozenset(paths)))
        for p in paths:
            ids.setdefault(p,len(ids))
    assert not logs
    return checked

def replay_scripts():
    for script in ("replay.py","summarize.py","continuation/evaluate.py"):
        subprocess.run([sys.executable, "-B", str(HERE/script), "--verify"], check=True,
                       stdout=subprocess.DEVNULL)

def storage_check():
    sys.path.insert(0,str(R54/"reserve"))
    from classic import SUFFIX
    from core import NOW
    db = sqlite3.connect(":memory:")
    db.executescript("""CREATE TABLE source(q,cid,score,PRIMARY KEY(q,cid)) WITHOUT ROWID;
                        CREATE INDEX ix_rank ON source(q,score DESC,cid);""")
    plans = [db.execute("EXPLAIN QUERY PLAN "+query,params).fetchall()[0][3]
             for query,params in ((NOW,("g",8)),(SUFFIX,("g",1,1,2,8)))]
    assert all("COVERING INDEX ix_rank" in p for p in plans), plans
    db.close()
    return plans

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--git",type=Path,help="Directory of pinned partial clones")
    ap.add_argument("--record",action="store_true")
    args=ap.parse_args()
    if args.record:
        assert args.git, "Create a full receipt only with independent Git verification."
    replay_scripts()
    sources = [read_json(HERE/p) for p in ("commits.json.gz","continuation/commits.json.gz")]
    diff_counts = {}
    if args.git:
        for source in sources:
            for project, record in source.items():
                diff_counts[project] = diff_check(args.git,project,record)
    events = read_json(HERE/"continuation/events.json.gz")["projects"]
    oracle = {p:check_conditional(p,s["revisions"],events[p]) for p,s in sources[1].items()}
    target_names = ("PROTOCOL_RU.md", "extract.py", "replay.py","summarize.py","commits.json.gz","events.json.gz",
                    "results.json","REPORT_RU.md","verify.py", "continuation/PROTOCOL_RU.md","continuation/extract_panel.py",
                    "continuation/pins.json","continuation/commits.json.gz","continuation/evaluate.py",
                    "continuation/events.json.gz","continuation/results.json","continuation/REPORT_RU.md")
    files = {p:sha256((HERE/p).read_bytes()).hexdigest() for p in target_names}
    report = {"files_sha256":files,"independent_anchor_checks":oracle,"ordered_index_plans":storage_check(),
              "all_projection_diffs":diff_counts,"metric_replays_verified":3}
    if args.record:
        write_json(HERE/"verification.json",report,False)
    else:
        expected = read_json(HERE/"verification.json")
        for k,v in report.items():
            if k != "all_projection_diffs" or args.git:
                assert expected[k] == v,k
    print("projection diffs",sum(diff_counts.values()), "reference anchors",sum(oracle.values()),"files",len(files))

if __name__ == "__main__":
    main()

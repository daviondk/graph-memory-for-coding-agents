"""Time durable writes and exact BM25 reads for five materialization schedules."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns as now

HERE = Path(__file__).resolve().parent
VIEW = HERE.parents[1] / "graph_memory_round25/query_view"
sys.path.insert(0, str(VIEW))
from make_fixture import DB, PRIVATE, decode, pack, read, write, sha
from ranking import bag, select
sys.path.insert(0, str(VIEW))
from term_index import encode, expand

METHODS = ("raw", "scan", "eager", "on_first", "on_third", "on_terms")
SCHEMA = """
CREATE TABLE win(s INTEGER, i INTEGER, body BLOB NOT NULL, PRIMARY KEY(s,i)) WITHOUT ROWID;
CREATE TABLE head(s INTEGER PRIMARY KEY, data BLOB NOT NULL);
CREATE TABLE term(s INTEGER, word TEXT, data BLOB NOT NULL, PRIMARY KEY(s,word)) WITHOUT ROWID;
"""
def priority(value):
    return hashlib.sha256(("online-index-v1/" + value).encode()).digest()

def open_database(path):
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.executescript(SCHEMA)
    return db

def counts(bodies):
    return [bag(body.decode("utf8")) for body in bodies]

def postings(documents, terms=None):
    table = defaultdict(list)
    if terms is not None:
        for term in terms:
            table[term] = []
    for i, document in enumerate(documents):
        for term, count in document.items():
            if terms is None or term in terms:
                table[term].append((i, count))
    return table

def save_postings(db, sid, table):
    records = [(sid, term, encode(group)) for term, group in sorted(table.items())]
    db.executemany("INSERT INTO term VALUES(?,?,?)", records)

def load_terms(db, sid, terms):
    if not terms:
        return {}
    markers = ",".join("?" for _ in terms)
    sql = f"SELECT word,data FROM term WHERE s=? AND word IN ({markers})"
    return {word: expand(blob) for word,blob in db.execute(sql, (sid, *terms))}

def write_episode(db, sid, coords, bodies, method):
    start = now()
    with db:
        db.executemany("INSERT INTO win VALUES(?,?,?)", ((sid,i,b) for i,b in enumerate(bodies)))
        # All layouts need the lengths. Count once while ingesting. The eager arm
        # reuses these frequencies for the durable index within this transaction.
        documents = counts(bodies) if method != "raw" else []
        lengths = [sum(doc.values()) for doc in documents]
        db.execute("INSERT INTO head VALUES(?,?)", (sid, pack([coords,lengths])))
        if method == "eager":
            save_postings(db, sid, postings(documents))
    return now() - start

def run_query(db, sid, query, method, number):
    start = now()
    coords, lengths = decode(db.execute("SELECT data FROM head WHERE s=?", (sid,)).fetchone()[0])
    view = {"rows": [{"coords": c, "length": n} for c,n in zip(coords,lengths)]}
    terms = sorted(bag(query))
    index_ready = method == "eager" or method == "on_first" and number > 1 or method == "on_third" and number > 3
    build_now = method == "on_first" and number == 1 or method == "on_third" and number == 3
    lists = load_terms(db,sid,terms) if index_ready or method == "on_terms" else {}
    missing = set(terms) - lists.keys()
    source_bytes = 0
    scan_now = build_now or (method == "on_terms" and bool(missing)) or (not index_ready and method != "on_terms")
    if scan_now:
        bodies = [row[0] for row in db.execute("SELECT body FROM win WHERE s=? ORDER BY i", (sid,))]
        source_bytes = sum(map(len,bodies))
        documents = counts(bodies)
        if method == "raw":
            view = {"rows":[{"coords": c,"length":sum(doc.values())} for c,doc in zip(coords,documents)]}
        if build_now:
            index = postings(documents)
            with db:
                save_postings(db,sid,index)
            lists = {w: dict(index.get(w,[])) for w in terms}
        elif method == "on_terms":
            delta = postings(documents,missing)
            with db:
                save_postings(db,sid,delta)
            lists.update({w: dict(v) for w,v in delta.items()})
        else:
            # A single SQL range scan; choose exactly the top BM25 window.
            lists = {w: dict(v) for w,v in postings(documents,set(terms)).items()}
    winner = select(view, query, "inverted", None, lists)
    return [now()-start, source_bytes, winner]

def main():
    src = sqlite3.connect(DB.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    registered = read(VIEW / "decisions.json.gz")
    ref = {(r["g"],r["q"]): r["ref"] for r in registered}
    snapshots = list(src.execute("SELECT sid,corpus FROM snapshot"))
    cohort = []
    for corpus, limit in (("isetrace",96),("squad",48)):
        cohort.extend((s,corpus) for s in sorted((s for s,c in snapshots if c==corpus),key=priority)[:limit])
    cohort.sort(key=lambda row: priority(row[0]))
    lock = {"cohort":cohort,"source":sha(DB),"protocol":sha(HERE/"PROTOCOL_RU.md"),"script":sha(Path(__file__)),
            "reference":sha(VIEW/"decisions.json.gz"),"sqlite":sqlite3.sqlite_version}
    lock_path = HERE/"plan.json"
    if lock_path.exists():
        assert read(lock_path) == lock
    else:
        write(lock_path,lock)
    rows=[]; files=[]
    for rep in range(3):
        with TemporaryDirectory(dir=PRIVATE) as tmp:
            paths={m:Path(tmp)/(m+".sqlite") for m in METHODS}
            dbs={m:open_database(p) for m,p in paths.items()}
            order=list(enumerate(cohort,1))
            random.Random(27541+rep).shuffle(order)
            for sid,(key,corpus) in order:
                meta=decode(src.execute("SELECT projected FROM snapshot WHERE sid=?",(key,)).fetchone()[0])
                coords=[r["coords"] for r in meta["rows"]]
                bodies=[v[0] for v in src.execute("SELECT body FROM payload WHERE sid=? ORDER BY idx",(key,))]
                queries=sorted(src.execute("SELECT q,question FROM future WHERE sid=?",(key,)),key=lambda r:priority(r[0]))
                assert len(queries)==(1 if corpus=="isetrace" else 11)
                shuffled=list(METHODS)
                random.Random(priority(str(rep)+key)).shuffle(shuffled)
                for method in shuffled:
                    db=dbs[method]; ingest=write_episode(db,sid,coords,bodies,method)
                    times=[]
                    for number,(q,query) in enumerate(queries,1):
                        elapsed,traffic,winner=run_query(db,sid,query,method,number)
                        assert winner==ref[key,q],(key,q,method,winner,ref[key,q])
                        times.append([q,elapsed,traffic,winner])
                    rows.append([rep,corpus,key,method,ingest,times])
            for method,db in dbs.items():
                pre=Path(str(paths[method])+"-wal").stat().st_size
                start=now();db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone(); checkpoint=now()-start
                assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
                physical=paths[method].stat().st_size
                structures=db.execute("select count(*) from term").fetchone()[0]
                db.close();files.append([rep,method,pre,checkpoint,physical,structures])
        print("completed repetition",rep,flush=True)
    src.close()
    write(HERE/"times.json.gz",rows);write(HERE/"files.json",files)
    write(HERE/"receipt.json",{"plan":sha(lock_path),"times":sha(HERE/"times.json.gz"),"files":sha(HERE/"files.json"),
            "runs":len(rows),"answers":sum(len(r[-1]) for r in rows)})
if __name__=="__main__":
    main()


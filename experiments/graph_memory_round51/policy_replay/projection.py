"""Produce the standalone SQLite projection used by the local demo server."""
import argparse
from pathlib import Path
import sqlite3
import replay

def write(path):
    if path.exists():
        raise FileExistsError("Choose a fresh output path")
    with sqlite3.connect(path) as db:
        replay.build(db)
        db.execute("CREATE TABLE questions(panel TEXT, question TEXT, label TEXT, PRIMARY KEY(panel,question)) WITHOUT ROWID")
        src=replay.R50/"address_demo"/"address.sqlite"
        with sqlite3.connect(src.as_uri()+"?mode=ro&immutable=1",uri=True) as address:
            labels=dict(address.execute("SELECT id,question FROM episode"))
        records=[]
        for (q,) in db.execute("SELECT question FROM routes WHERE panel='gate_confirmation'"):
            records.append(("gate_confirmation",q,labels[replay.digest(q.encode())[:16]]))
        db.executemany("INSERT INTO questions VALUES(?,?,?)",records)
        db.commit()
    print(replay.digest(path.read_bytes()))

if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument("path",type=Path)
    write(arg.parse_args().path)


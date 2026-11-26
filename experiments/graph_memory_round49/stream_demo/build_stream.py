"""Create a read-only SQLite projection from a digest-selected sample of real streams."""
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sqlite3

D = Path(__file__).resolve().parent
def main():
    source = D.parent / "stream_packet" / "input.json.gz"
    digest = sha256(source.read_bytes()).hexdigest()
    assert digest == "b527263345d7d07dea1f9a33c556803663fb4a3e6e1cad67e3fcba399da47d4f"
    inputs = json.loads(gzip.decompress(source.read_bytes()))
    dbfile = D/"apps/stream/observations.sqlite"
    if dbfile.exists():
        raise FileExistsError("Build into a new copy without an existing projection")
    db = sqlite3.connect(dbfile)
    with db:
        db.executescript("""
          CREATE TABLE history(id TEXT PRIMARY KEY, question_hash TEXT, steps INT);
          CREATE TABLE unit(history TEXT, seq INT, born INT, id INT, cost INT, utility INT,
                            owners TEXT, PRIMARY KEY(history,seq)) WITHOUT ROWID;
          CREATE TABLE witness(history TEXT, step INT, owner INT, count INT,
                               PRIMARY KEY(history,step,owner)) WITHOUT ROWID;
        """)
        for label, lo, hi in (("Short",10,16),("Medium",24,32),("Long",35,55)):
            q = next(q for q in sorted(inputs) if lo<=len(inputs[q][2])<=hi and 65<=len(inputs[q][1])<=180)
            _, units, events = inputs[q]
            db.execute("INSERT INTO history VALUES(?,?,?)",(label,q,len(events)))
            db.executemany("INSERT INTO unit VALUES(?,?,?,?,?,?,?)",
                [(label,j,b,i,c,v,json.dumps(o)) for j,(b,i,c,v,o) in enumerate(units)])
            db.executemany("INSERT INTO witness VALUES(?,?,?,?)",
                [(label,t,src,k) for t,changes in enumerate(events,1) for src,k in changes])
            print(label,q,len(units),len(events))
    db.close()
if __name__ == "__main__":
    main()

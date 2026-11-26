"""Materialize a blinded trace projection and store annotations in separate SQLite tables."""
import gzip,hashlib,json,sqlite3
from pathlib import Path
from statistics import median
import numpy as np
D=Path(__file__).resolve().parent
BASE=D.parent/"matched_reader"
VOTES=D.parent/"packet_consensus"
STREAM=D.parents[1]/"graph_memory_round49/stream_packet"

def signed(directory,name):
    p=directory/name;raw=p.read_bytes()
    m=json.loads((directory/"manifest.json").read_bytes())
    assert hashlib.sha256(raw).hexdigest()==m.get("files",m)[name]
    return gzip.decompress(raw) if name.endswith(".gz") else raw

def main():
    seed_order=[13,17,29,37,41]
    pool=json.loads(signed(BASE,"pool.json.gz"))
    chosen=sorted(pool,key=lambda q:hashlib.sha256(("demo-visible-graph-v1|"+q).encode()).digest())[:32]
    ranks=[json.loads(signed(BASE,f"ranks-{s}.json.gz")) for s in seed_order]
    ballots=[json.loads(signed(BASE,f"archive-{s}.json.gz")) for s in seed_order]
    utils=[np.frombuffer(signed(BASE,f"utility-{s}.f64.gz"),dtype="<f8") for s in seed_order]
    obs=json.loads(signed(VOTES,"packets.json.gz"))
    gold=json.loads(signed(STREAM,"judgments.json.gz"))
    dest=D/"consensus.sqlite";assert not dest.exists()
    with sqlite3.connect(dest) as db:
        db.executescript("""
        CREATE TABLE question(id INTEGER PRIMARY KEY, benchmark_id TEXT UNIQUE NOT NULL, trajectory TEXT NOT NULL);
        CREATE TABLE unit(q INTEGER NOT NULL, u INTEGER NOT NULL,cost INTEGER NOT NULL, role TEXT NOT NULL,
                          PRIMARY KEY(q,u)) WITHOUT ROWID;
        CREATE TABLE reader(q INTEGER NOT NULL,u INTEGER NOT NULL,seed INTEGER NOT NULL,
                            rank INTEGER NOT NULL,utility REAL NOT NULL,voted INTEGER NOT NULL,
                            PRIMARY KEY(q,u,seed)) WITHOUT ROWID;
        CREATE TABLE official_span(q INTEGER NOT NULL,atom INTEGER NOT NULL,width INTEGER NOT NULL,
                                   PRIMARY KEY(q,atom)) WITHOUT ROWID;
        CREATE TABLE official_member(q INTEGER NOT NULL,atom INTEGER NOT NULL,u INTEGER NOT NULL,
                                     PRIMARY KEY(q,atom,u)) WITHOUT ROWID;
        CREATE TABLE reference(q INTEGER NOT NULL,method TEXT NOT NULL,ids TEXT NOT NULL,
                               PRIMARY KEY(q,method)) WITHOUT ROWID;
        """)
        offset=0
        for q,r in sorted(pool.items()):
            n=len(r["c"]);end=offset+n
            if q in chosen:
                case=chosen.index(q)+1
                db.execute("INSERT INTO question VALUES(?,?,?)",(case,q,r["t"]))
                db.executemany("INSERT INTO unit VALUES(?,?,?,?)",
                    [(case,i,int(c),"output" if r["x"][i][2] else "argument") for i,c in enumerate(r["c"])])
                for j,s in enumerate(seed_order):
                    order=ranks[j][q][1]
                    vote=set(ballots[j][q][0][0])
                    db.executemany("INSERT INTO reader VALUES(?,?,?,?,?,?)",[(case,i,s,k+1,float(utils[j][offset+i]),int(i in vote)) for k,i in enumerate(order)])
                atoms=gold[hashlib.sha256(q.encode()).hexdigest()]
                for a,(width,members) in enumerate(atoms):
                    db.execute("INSERT INTO official_span VALUES(?,?,?)",(case,a,width))
                    db.executemany("INSERT INTO official_member VALUES(?,?,?)",[(case,a,i) for i in members])
                db.executemany("INSERT INTO reference VALUES(?,?,?)",
                    [(case,k,json.dumps(obs[q][1][0][k])) for k in ("votes_greedy","hamming_dp","mean_dp","votes_dp")])
            offset=end
        assert all(offset==len(u) for u in utils)
        db.commit()
        print(db.execute("SELECT count(*) FROM question").fetchone(),db.execute("SELECT count(*) FROM reader").fetchone())
if __name__=="__main__":main()


from pathlib import Path
import hashlib,json,gzip,sqlite3
D=Path(__file__).resolve().parent
PARENT=D.parent/"deferred_revocation"
def canonical(z):return (json.dumps(z,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def save(p,z):
    b=canonical(z);p.write_bytes(gzip.compress(b,compresslevel=6,mtime=0) if p.suffix==".gz" else b)
def load(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hkey(t):return hashlib.sha256(("recover-r35/v1/"+t).encode()).hexdigest()
def original():
    manifest=load(PARENT/"manifest.json");files=manifest.get("files",manifest);allrows={};hs={}
    for p in sorted(PARENT.glob("operations-*.json.gz")):
        hs[p.name]=sha(p);assert files[p.name]==hs[p.name];allrows.update(load(p))
    assert len(hs)==8 and len(allrows)==1207
    return [allrows[t]["log"] for t in sorted(allrows,key=hkey)[:64]],sorted(map(hkey,allrows))[:64],hs
def source():
    return sqlite3.connect((D/"source.sqlite3").as_uri()+"?mode=ro&immutable=1",uri=True)
def fetch(db,h,lo,hi):
    for seq,c,ins,rm in db.execute("SELECT seq,cut,added,removed FROM events WHERE hid=? AND seq>? AND seq<=? ORDER BY seq",(h,lo,hi)):
        yield seq,bool(c),json.loads(ins),json.loads(rm)
def newdb(path):
    db=sqlite3.connect(path,isolation_level=None)
    assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0]=="wal";db.execute("PRAGMA synchronous=FULL");db.execute("PRAGMA wal_autocheckpoint=0")
    assert db.execute("PRAGMA synchronous").fetchone()==(2,)
    return db
def openbase(path):
    db=newdb(path);db.executescript("BEGIN IMMEDIATE; CREATE TABLE edge(id INTEGER PRIMARY KEY); CREATE TABLE barrier(id INTEGER PRIMARY KEY CHECK(id=1), seq INTEGER NOT NULL); INSERT INTO barrier VALUES(1,0); COMMIT;");return db
def snapshot(db):return [r[0] for r in db.execute("SELECT id FROM edge ORDER BY id")]
def watermark(db):return db.execute("SELECT seq FROM barrier WHERE id=1").fetchone()[0]

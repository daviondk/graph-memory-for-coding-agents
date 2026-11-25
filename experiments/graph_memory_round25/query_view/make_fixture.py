"""Build projections at observation time. Later questions are kept in a separate table."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zlib
D=Path(__file__).resolve().parent
SOURCE=D.parent/"directional_open"
sys.path.insert(0,str(SOURCE))
from dataset import ise_visible,squad_rows,squad_frags,Tokenizer,TOK
from novelty import make_windows
from ranking import write_view,sizes
sys.path.insert(0,str(D.parents[1]/"graph_memory_round23/read_causes"))
from project import read,write,sha

PRIVATE=Path("D:/CodexResearch/x20-query-projection-sql")
DB=PRIVATE/"query-views.sqlite"
def pack(obj):
    return zlib.compress(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode(),6)
def decode(blob):
    return json.loads(zlib.decompress(blob))
def priority(q):
    return hashlib.sha256(("query-view-v1/"+q).encode()).digest()
def build(conn,corpus,context,first,initial,fragments,lens,future,tok):
    sid=hashlib.sha256((corpus+"/"+context+"/"+first).encode()).hexdigest()
    windows=[]
    for e,l,txt in fragments:
        edge=l+len(txt)
        for w in make_windows([(e,l,txt)],tok):
            windows.append({"e":e,"l":w.start,"h":w.end,"edge":edge,"eligible":edge<lens[e],"text":w.text})
    view,full=write_view(windows,initial)
    size=sizes(view,full)
    invert=defaultdict(dict)
    for i,doc in enumerate(full):
        for w,f in doc.items():invert[w][i]=f
    body_size=sum(len(w["text"].encode()) for w in windows)
    conn.execute("INSERT INTO snapshot VALUES(?,?,?,?,?,?,?,?)",(sid,corpus,context,first,pack(view),pack(invert),pack(size),body_size))
    conn.executemany("INSERT INTO payload VALUES(?,?,?)",[(sid,i,w["text"].encode()) for i,w in enumerate(windows)])
    conn.executemany("INSERT INTO future VALUES(?,?,?)",[(sid,q,txt) for q,txt in future])
    return {"key":sid,"corpus":corpus,"first":first,"future":[q for q,txt in future],"windows":len(windows),"source_bytes":body_size,"index_bytes":size}

def main():
    PRIVATE.mkdir(exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(dir=PRIVATE) as tmp:
        stage=Path(tmp)/"fresh.sqlite";conn=sqlite3.connect(stage)
        conn.executescript("""
        CREATE TABLE snapshot(sid TEXT PRIMARY KEY,corpus TEXT,context TEXT,q0 TEXT,projected BLOB,inverted BLOB,costs BLOB,body_size INTEGER) WITHOUT ROWID;
        CREATE TABLE payload(sid TEXT,idx INTEGER,body BLOB,PRIMARY KEY(sid,idx)) WITHOUT ROWID;
        CREATE TABLE future(sid TEXT,q TEXT,question TEXT,PRIMARY KEY(sid,q)) WITHOUT ROWID;
        """)
        tok=Tokenizer.from_file(str(TOK)); groups=defaultdict(list);records=[]
        for q,t,query,frags,lens,fee,shard in ise_visible():
            groups[t].append((q,query,frags,lens))
        for t,items in sorted(groups.items()):
            ordered=sorted(items,key=lambda r:priority(r[0]))
            if len(ordered)<2:continue
            q,x,frags,lens=ordered[0]
            records.append(build(conn,"isetrace",t,q,x,frags,lens,[(r[0],r[1]) for r in ordered[1:]],tok))
        for name,body,questions in sorted(squad_rows()):
            ordered=sorted(questions,key=lambda r:priority(r[0]))
            q,query,fragments,_=next(squad_frags(tok,body,ordered[:1]))
            records.append(build(conn,"squad",name,q,query,fragments,{0:len(body)},ordered[1:],tok))
        conn.commit(); assert conn.execute("pragma integrity_check").fetchone()==("ok",)
        conn.execute("VACUUM");conn.close()
        if DB.exists():assert sha(DB)==sha(stage)
        else:stage.replace(DB)
    write(D/"cohort.json.gz",records)
    write(D/"input-lock.json",{"private_sqlite":sha(DB),"sqlite_bytes":DB.stat().st_size,
         "cohort":sha(D/"cohort.json.gz"),"protocol":sha(D/"PROTOCOL_RU.md"),"writer":sha(Path(__file__)),
         "methods":sha(D/"ranking.py"),"tokenizer":sha(TOK)})
    for corpus in ("isetrace","squad"):
        rec=[r for r in records if r["corpus"]==corpus]
        print(corpus,len(rec),sum(len(r["future"]) for r in rec),sum(r["windows"] for r in rec))
if __name__=="__main__":main()

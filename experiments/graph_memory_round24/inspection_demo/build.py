"""Build a coordinate-only replay; never write trace text, questions, commands, or paths."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

D=Path(__file__).resolve().parent
W=D.parents[1];R=W/"graph_memory_round23";M=R/"marginal_open";P=R/"read_causes";REC=R/"receiver_merge";A=R/"address_open"
sys.path.insert(0,str(M));from novelty import make_windows,lexical_order,choose
sys.path.insert(0,str(A));from choose import paid_open,CACHE,TOK,Tokenizer
def read(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)
def digest(x):return hashlib.sha256(x).hexdigest()
def sha(p):return digest(p.read_bytes())
def save(p,x):
    raw=(json.dumps(x,separators=(",",":"),sort_keys=True,ensure_ascii=False)+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)
def cid(q):return "Q-"+digest(("r24-inspect:"+q).encode())[:8].upper()
def select():
    stats=read(M/"per-query.json.gz")
    order=sorted(stats,key=cid)
    pos=lambda q:stats[q]["arms"]["first_positive"]
    bm=lambda q:stats[q]["arms"]["bm25"]
    chosen={}
    def add(title,k,f):
        for q in [q for q in order if q not in chosen and f(q)][:k]:chosen[q]=title
    add("additional",3,lambda q:pos(q)["union_fs"]>bm(q)["union_fs"])
    add("bm25",2,lambda q:pos(q)["union_fs"]<bm(q)["union_fs"])
    add("no_read",2,lambda q:bool(pos(q)["abstained"]))
    add("duplicate",2,lambda q:bm(q)["issued_zero_new"] and pos(q)["gold_gain_chars"]==0)
    add("hash",12,lambda q:True)
    assert 15<=len(chosen)<=21 and "additional" in chosen.values()
    return chosen
def checked(lock,base,name):
    f=base/name
    assert sha(f)==lock[name],name
    return read(f)
def maps():
    rim=read(P/"receipt-lock.json")["files"];rc=read(REC/"receiver-lock.json")["files"]
    orig=read(A/"read-lock.json")["files"];marg={f:h for f,h,_ in read(M/"opened-seal.json")["files"]}
    return rim,rc,orig,marg
def generate():
    picked=select();seals=maps();reg=sqlite3.connect((P/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    lengths=sqlite3.connect((M/"field-lengths.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    tok=Tokenizer.from_file(str(TOK));snap={};counts=defaultdict(int)
    for i in range(8):
        source,recv,base,marg=(checked(seals[j],loc,name) for j,(loc,name) in enumerate(((P,f"receipts-{i}.json.gz"),(REC,f"receiver-{i}.json.gz"),(A,f"reads-{i}.json.gz"),(M,f"opened-{i}.json.gz"))))
        marg={x["q"]:x for x in marg}
        for r in source:
            q=r["q"]
            if q not in picked:continue
            t=r["t"]; rr=recv[q]; assert rr["t"]==t==marg[q]["t"]==base[q]["t"]
            raw=read(CACHE/f"{i}-{t}.json.gz");query=dict(raw["q"])[q];fields=raw["fields"]
            addr=dict(reg.execute("SELECT e,eid FROM address WHERE t=?",(t,)))
            scope={e:fields[key] for e,key in addr.items()}
            limits=dict(lengths.execute("SELECT e,n FROM field_size WHERE t=?",(t,)))
            assert all(len(v)==limits[e] for e,v in scope.items())
            fmt={}
            def item(key):
                x=r["arms"]["ratio/"+key]["paid"]["2048"]
                return x[2],x[0],x[0],x[1]
            short=item("short");sender=item("merged")
            for name,(units,wire,internal,wire_bytes) in (("short",short),("sender",sender),("receiver",(rr["shown"],rr["tokens_in"],rr["tokens_internal"],short[3]))):
                windows=make_windows([(e,a,scope[e][a:b]) for e,a,b in units],tok)
                ranking=lexical_order(query,windows)
                spans=defaultdict(list)
                for e,a,b in units:spans[e].append((a,b))
                ix,detail=choose(windows,ranking,spans,limits,[len(tok.encode(f"[{w.field}:{w.start}] ",add_special_tokens=False).ids) for w in windows])
                actions={}
                for policy in ("bm25","first_positive"):
                    j=ix[policy];op=None
                    if j is not None:
                        w=windows[j];e=w.field;a=w.start
                        z=reg.execute("SELECT eid,ptr FROM address WHERE t=? AND e=?",(t,e)).fetchone()
                        assert z and z[0]==addr[e]
                        op=paid_open(tok,fields[z[0]],e,a)
                    if name=="sender":
                        assert op==marg[q]["open"][policy];counts["r23"]+=1
                    elif policy=="bm25":
                        upstream=(rr["opened"] if name=="receiver" else base[q]["read"]["ratio/short/bm25"])
                        assert (op or [-1,0,0,0])==upstream;counts["r23"]+=1
                    else:counts["new"]+=1
                    actions[policy]={"open":op,"predicted":None if j is None else detail[j][1],"rank":None if j is None else ranking.index(j)+1,
                                     "lineage":"R23" if name=="sender" or policy=="bm25" else "R24"}
                fmt[name]={"wire":wire,"internal":internal,"wire_bytes":wire_bytes,"memory":units,"options":actions}
            snap[cid(q)]={"category":picked[q],"formats":fmt}
    reg.close();lengths.close()
    assert len(snap)==len(picked)
    save(D/"actions.json.gz",snap);save(D/"action-seal.json",{"actions":sha(D/"actions.json.gz"),"counts":counts,"cases":len(snap),
         "code":sha(Path(__file__)),"parents":{str(f.relative_to(R)):sha(f) for f in (P/"receipt-lock.json",REC/"receiver-lock.json",A/"read-lock.json",M/"opened-seal.json",M/"choice-seal.json",M/"novelty.py",M/"per-query.json.gz")}})
    print("sealed",len(snap),dict(counts))
SCHEMA="""
CREATE TABLE sample(id TEXT PRIMARY KEY, mode TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE source_span(case_id TEXT, kind TEXT, fmt TEXT, ordinal INTEGER, field_no INTEGER, a INTEGER, b INTEGER, PRIMARY KEY(case_id,kind,fmt,ordinal)) WITHOUT ROWID;
CREATE TABLE memory(case_id TEXT,fmt TEXT,wire_wp INTEGER,inside_wp INTEGER,wire_bytes INTEGER,PRIMARY KEY(case_id,fmt)) WITHOUT ROWID;
CREATE TABLE decision(case_id TEXT,fmt TEXT,policy TEXT,field_no INTEGER,a INTEGER,predicted INTEGER,rank INTEGER,origin TEXT,PRIMARY KEY(case_id,fmt,policy)) WITHOUT ROWID;
CREATE TABLE observed_open(case_id TEXT,field_no INTEGER,a INTEGER,b INTEGER,paid_wp INTEGER,PRIMARY KEY(case_id,field_no,a)) WITHOUT ROWID;
"""
def build():
    seal=read(D/"action-seal.json");assert sha(D/"actions.json.gz")==seal["actions"]
    snap=read(D/"actions.json.gz");qs=select()
    gt=W/"graph_memory_round18/isetrace_official/gold-spans.json.gz"
    cohort={r["query_id"]:r for r in read(gt.with_name("cohort.json"))};gold=read(gt)
    src=sqlite3.connect((P/"registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    file=D/"inspection.sqlite"; staging=D/"inspection-temp.sqlite"
    if staging.exists():raise FileExistsError(staging)
    db=sqlite3.connect(staging);db.executescript(SCHEMA)
    with db:
        for q,reason in qs.items():
            key=cid(q);row=snap[key];co=cohort[q];t=co["trajectory_id"]
            db.execute("INSERT INTO sample VALUES(?,?,?)",(key,co["memory_mode"],reason))
            for j,s in enumerate(gold[q]):
                p=src.execute("SELECT e FROM address WHERE t=? AND eid=? AND ptr=?",(t,s["event_id"],s["json_pointer"])).fetchone()
                # A gold field unregistered in the available pool still counts in recall.
                if not p:raise ValueError("Annotation in absent field; need a distinct redacted id")
                db.execute("INSERT INTO source_span VALUES(?,?,?,?,?,?,?)",(key,"gold","",j,p[0],s["char_start"],s["char_end"]))
            for fmt,rep in row["formats"].items():
                db.execute("INSERT INTO memory VALUES(?,?,?,?,?)",(key,fmt,rep["wire"],rep["internal"],rep["wire_bytes"]))
                db.executemany("INSERT INTO source_span VALUES(?,?,?,?,?,?,?)",[(key,"memory",fmt,j,*p) for j,p in enumerate(rep["memory"])])
                for name,a in rep["options"].items():
                    op=a["open"];e,l=(op[:2] if op else [None,None])
                    db.execute("INSERT INTO decision VALUES(?,?,?,?,?,?,?,?)",(key,fmt,name,e,l,a["predicted"],a["rank"],a["lineage"]))
                    if op:
                        prev=db.execute("SELECT b,paid_wp FROM observed_open WHERE case_id=? AND field_no=? AND a=?",(key,e,l)).fetchone()
                        if prev:assert list(prev)==op[2:]
                        else:db.execute("INSERT INTO observed_open VALUES(?,?,?,?,?)",(key,*op))
    assert db.execute("pragma integrity_check").fetchone()[0]=="ok"
    db.execute("vacuum");db.close();src.close()
    if file.exists():
        assert sha(file)==sha(staging);staging.unlink()
    else:staging.replace(file)
    print("DB",sha(file),file.stat().st_size)
if __name__=="__main__":
    {"generate":generate,"build":build}[sys.argv[1]]()

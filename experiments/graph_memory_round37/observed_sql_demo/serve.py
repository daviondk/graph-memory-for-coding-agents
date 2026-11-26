"""Serve a loopback-only, read-only SQLite observation explorer."""
from pathlib import Path
from contextlib import contextmanager,closing
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
import argparse,json,re,sqlite3,sys
D=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(D/"operators/range_read"))
import query

@contextmanager
def dbpair():
    def opened(name):
        db=sqlite3.connect((D/name).resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
        db.execute("PRAGMA query_only=ON")
        return db
    with closing(opened("eager.db")) as eager,closing(opened("inverse.db")) as lazy:
        yield eager,lazy

def catalogue(db):
    return {key:json.loads(raw) for key,raw in db.execute("SELECT k,case_json FROM demo ORDER BY k")}
def public(case):
    return {k:v for k,v in case.items() if k!="path"}
def digest(rows):
    packed=[[n,s.hex()] for n,s in rows]
    return sha256(json.dumps(packed,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def evidence(db,e):
    return (dict(db.execute("SELECT n,s FROM f WHERE e=? ORDER BY n",(e,))),
            dict(db.execute("SELECT n,s FROM r WHERE e=? ORDER BY n",(e,))))
def edit(db,e):return db.execute("SELECT k,z,d,overflow FROM v WHERE e=?",(e,)).fetchone()
def source(db,c):
    e=c["id"];base,receipt=evidence(db,e);k,z,d,crowded=edit(db,e)
    return public(c)|dict(start=k,end=z,delta=d,overflow=bool(crowded),
        base=[[n,s.hex()] for n,s in base.items()],receipt=[[n,s.hex()] for n,s in receipt.items()])
def read_window(dbs,item,lo,hi):
    e=item["id"]; lazy=dbs[1];stats={};answers={}
    for arm in ("eager_index","inverse"):
        pairs,num=query.read(dbs,arm,e,item,lo,hi)
        stats[arm]=dict(db_rows=num,hash_bytes=32*(num-int(arm=="inverse")),answer_digest=digest(pairs))
        answers[arm]=pairs
    if answers["eager_index"]!=answers["inverse"]:raise RuntimeError("Native operators disagree.")
    pairs=answers["inverse"];current=dict(pairs)
    # These extra lookups explain provenance and gaps. They are outside both operator counters.
    base,receipt=evidence(lazy,e);k,z,d,crowded=edit(lazy,e)
    present=[];missing={}
    for n in range(lo,hi+1):
        pre=None
        if k is not None:
            if n<k:pre=n
            elif n-d>z:pre=n-d
        if n in current:
            kind="receipt" if n in receipt else ("shifted" if pre!=n else "carried")
            assert (receipt[n] if kind=="receipt" else base[pre])==current[n]
            present.append(dict(n=n,hash=current[n].hex(),origin=kind,before=None if kind=="receipt" else pre))
        elif pre is not None and pre in base:
            assert crowded and n not in receipt
            missing[n]="evicted"
        elif k is not None and k<=n<=z+d:
            missing[n]="replaced"
        else:
            missing[n]="unobserved"
    gaps=[]
    for n,why in missing.items():
        if gaps and gaps[-1]["reason"]==why and gaps[-1]["hi"]==n-1:gaps[-1]["hi"]=n
        else:gaps.append(dict(lo=n,hi=n,reason=why))
    return dict(case=item["label"],lo=lo,hi=hi,rows=present,gaps=gaps,stats=stats,overflow=bool(crowded))

def digit(text):
    if not re.fullmatch(r"[1-9][0-9]{0,5}",text or ""):raise ValueError("Use positive whole line numbers.")
    return int(text)
def endpoint(path,q):
    expected={"/api/cases":set(),"/api/source":{"case"},"/api/read":{"case","lo","hi"}}
    if path not in expected:raise KeyError("Unknown endpoint.")
    if set(q)!=expected[path] or any(len(v)!=1 for v in q.values()):raise ValueError("Unexpected or missing parameters.")
    with dbpair() as dbs:
        c=catalogue(dbs[1])
        if path=="/api/cases":return [public(row) for row in sorted(c.values(),key=lambda v:v["id"])]
        if q["case"][0] not in c:raise ValueError("Unknown case.")
        case=c[q["case"][0]]
        if path=="/api/source":return source(dbs[1],case)
        lo,hi=digit(q["lo"][0]),digit(q["hi"][0])
        if not 1<=lo<=hi<=100000 or hi-lo+1>512:raise ValueError("Enter a range of 1–512 lines, between 1 and 100,000.")
        return read_window(dbs,case,lo,hi)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def emit(self,status,mime,data):
        self.send_response(status);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'")
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        url=urlsplit(self.path)
        files={"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript; charset=utf-8"),"/style.css":("style.css","text/css; charset=utf-8")}
        if url.path in files and not url.query:
            name,mime=files[url.path];return self.emit(200,mime,(D/name).read_bytes())
        try:
            ans=endpoint(url.path,parse_qs(url.query,keep_blank_values=True))
            code=200
        except KeyError:
            code=404;ans={"error":"Unknown endpoint."}
        except ValueError as exc:
            code=400;ans={"error":str(exc)}
        self.emit(code,"application/json; charset=utf-8",json.dumps(ans,ensure_ascii=False).encode())
def service(port=0):
    return ThreadingHTTPServer(("127.0.0.1",port),Handler)
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--port",type=int,default=8781)
    with service(parser.parse_args().port) as server:
        print(f"Open http://127.0.0.1:{server.server_port}/   Stop with Ctrl+C.",flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass

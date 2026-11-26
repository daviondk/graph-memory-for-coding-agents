"""Offline inspection of a strict-context trace, one verified next-read replay and an opt-in audit."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parent
METHODS={"rrf":"Three static lists","suggested":"First valid suggestion","confirmed":"Corroborated suggestion",
         "memory_rrf":"Static RRF + suggestions","static_four":"Static RRF + 8B"}
def connect(name):
    db=sqlite3.connect((ROOT/name).as_uri()+"?mode=ro&immutable=1",uri=True);db.row_factory=sqlite3.Row;return db
def cases(db):
    ls=[dict(x) for x in db.execute("SELECT q,repo,revision,task FROM episode ORDER BY seq")]
    return dict(examples=ls,default_q=ls[0]["q"],methods=METHODS)
SQL="""
WITH scored AS (
 SELECT p.h AS id,p.name AS path,c.ord,c.proposed AS suggestion_rank,
        c.lexical,c.repomap,c.embed4,c.embed8,
        COALESCE(1.0/(60+c.lexical),0)+COALESCE(1.0/(60+c.repomap),0)+COALESCE(1.0/(60+c.embed4),0) AS static_score,
        (c.lexical IS NOT NULL OR c.repomap IS NOT NULL OR c.embed4 IS NOT NULL) AS supported
 FROM candidate c JOIN path p USING(q,h) WHERE c.q=:q
), methods AS (
 SELECT *,static_score + CASE :method
   WHEN 'memory_rrf' THEN COALESCE(1.0/(60+suggestion_rank),0)
   WHEN 'static_four' THEN COALESCE(1.0/(60+embed8),0) ELSE 0 END AS score,
   CASE WHEN :method='suggested' OR (:method='confirmed' AND supported)
        THEN suggestion_rank ELSE NULL END AS priority
 FROM scored)
SELECT * FROM methods ORDER BY (priority IS NULL),priority,score DESC,ord
"""
PACKET="""
SELECT p.h AS id,p.name AS path,v.entered FROM (
 SELECT h,0 AS entered FROM origin WHERE q=:q AND strict=1 UNION ALL
 SELECT :chosen AS h,1 AS entered WHERE :version=1
) v JOIN path p ON p.q=:q AND p.h=v.h ORDER BY v.entered,p.name
"""
def state(db,params):
    if set(params)-{"q","method","version"}:raise ValueError("Unknown parameter")
    q=params.get("q") or db.execute("SELECT q FROM episode ORDER BY seq LIMIT 1").fetchone()[0]
    method=params.get("method","rrf");raw=params.get("version","0")
    if method not in METHODS or raw not in ("0","1"):raise ValueError("Invalid method or version")
    ref=db.execute("SELECT repo,revision,task FROM episode WHERE q=?",(q,)).fetchone()
    if ref is None:raise ValueError("Unknown trace")
    ranking=[dict(r) for r in db.execute(SQL,dict(q=q,method=method))]
    chosen=ranking[0];ver=int(raw);h=chosen["id"]
    receipt=db.execute("SELECT first_line,last_line,text_sha256 FROM receipt WHERE q=? AND h=?",(q,h)).fetchone()
    if receipt is None:raise RuntimeError("Selected path missing a verified receipt")
    strict=[dict(r) for r in db.execute(PACKET,dict(q=q,chosen=h,version=ver))]
    proposals=[dict(r) for r in db.execute("""SELECT s.h AS id,COALESCE(p.name,s.h) AS path,s.rank,s.eligible,s.previously_read
                FROM proposal s LEFT JOIN path p USING(q,h) WHERE s.q=? ORDER BY s.rank""",(q,))]
    opened=[dict(r) for r in db.execute("SELECT p.h AS id,p.name AS path,o.strict FROM origin o JOIN path p USING(q,h) WHERE o.q=? ORDER BY p.name",(q,))]
    return dict(q=q,**dict(ref),method=method,version=ver,selected=chosen,ranking=ranking,proposals=proposals,
        context=strict,archived_reads=opened,receipt=dict(receipt) if ver else None)
def evaluation(result):
    with closing(connect("audit.sqlite")) as db:
        gold={r[0] for r in db.execute("SELECT h FROM required WHERE q=?",(result["q"],))}
    selected=result["selected"]["id"];current={x["id"] for x in result["context"]};hits=sorted(current&gold)
    return dict(q=result["q"],method=result["method"],version=result["version"],total_gold=len(gold),covered=len(hits),
                recall=len(hits)/len(gold),complete=gold<=current,new_hit=bool(result["version"] and selected in gold),hit_ids=hits)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,mime,data):
        self.send_response(code);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(data)
    def handle_api(self,post):
        url=urlsplit(self.path)
        if not post and url.path=="/":self.reply(200,"text/html; charset=utf-8",(ROOT/"index.html").read_bytes());return
        try:
            args=parse_qs(url.query,keep_blank_values=True,max_num_fields=5)
            if any(len(v)!=1 for v in args.values()):raise ValueError("Duplicate parameter")
            params={k:v[0] for k,v in args.items()}
            if (post and url.path!="/api/evaluate") or (not post and url.path not in ("/api/state","/api/cases")):
                self.reply(404,"text/plain",b"Unknown route");return
            with closing(connect("trace.sqlite")) as db:
                if url.path=="/api/cases":
                    if params:raise ValueError("No controls for the case list")
                    result=cases(db)
                else:result=state(db,params)
            if post:result=evaluation(result)
            status=200
        except ValueError as exc:status=400;result=dict(error=str(exc))
        self.reply(status,"application/json; charset=utf-8",json.dumps(result,ensure_ascii=False,allow_nan=False).encode())
    def do_GET(self):self.handle_api(False)
    def do_POST(self):self.handle_api(True)
if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument("--port",type=int,default=0)
    with ThreadingHTTPServer(("127.0.0.1",cli.parse_args().port),Handler) as http:
        print(f"http://127.0.0.1:{http.server_port}/",flush=True)
        try:http.serve_forever()
        except KeyboardInterrupt:pass

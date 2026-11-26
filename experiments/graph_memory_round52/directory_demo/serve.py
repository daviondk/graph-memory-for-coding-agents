"""Local, standard-library SQLite replay for eight full-directory address traces."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import sqlite3
import unicodedata
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
GATES = {"off": -1, "0": 0, "59": 59, "5989": 5989}
DEFAULT_Q = "3e5580c00bb011ebab90acde48001122"
MODES = {"href", "literal", "none"}
RANK = """
WITH flags AS (
  SELECT *, (:limit>=0 AND (direct_words>=2 OR (direct_words=1 AND df BETWEEN 1 AND :limit))) AS direct,
         CASE :mode WHEN 'href' THEN href WHEN 'literal' THEN literal ELSE 0 END AS edge
  FROM candidates WHERE q=:q
), routes AS (
  SELECT *, CASE WHEN direct THEN 0 WHEN edge AND id!=:omit THEN 1 WHEN base THEN 2 ELSE 3 END AS tier
  FROM flags
)
SELECT id,title,page,score,literal,href,base,direct_words,df,anchor,direct,edge,tier
FROM routes ORDER BY tier,score DESC,page,id
"""
def cases(db):
    rows = db.execute("SELECT q,scenario,seed FROM episodes ORDER BY q").fetchall()
    examples = [dict(q=r["q"], scenario=r["scenario"].split("-")[0], seed=r["seed"]) for r in rows]
    return dict(examples=examples,default_q=DEFAULT_Q,directory_size=5989847)

def normalize(title):
    return unicodedata.normalize("NFC"," ".join(title.replace("_"," ").split()))

def words(text):
    return re.findall(r"[^\W_]+",unicodedata.normalize("NFKC",text).lower())

def witness(best,route,episode):
    if route=="href":return dict(kind="anchor",text=best["anchor"])
    if route=="directory":return dict(kind="baseline title lookup",text=best["title"])
    observed=words(episode["question"] if route=="question" else episode["prefix"])
    title=words(best["title"]);blocked=set()
    if route=="question":
        seed=words(episode["seed"])
        for i in range(len(observed)-len(seed)+1):
            if observed[i:i+len(seed)]==seed:blocked.update(range(i,i+len(seed)))
    for start in range(len(observed)-len(title)+1):
        end=start+len(title)
        if observed[start:end]==title and blocked.isdisjoint(range(start,end)):
            return dict(kind="question span" if route=="question" else "literal passage span",text=" ".join(title),start=start,end=end)
    raise AssertionError("Missing visible span in stored projection")

def selection(db, params):
    unknown=set(params)-{"q","gate","mode","suppress"}
    if unknown:raise ValueError("Unknown control")
    gate=params.get("gate","59");mode=params.get("mode","href")
    if gate not in GATES or mode not in MODES:raise ValueError("Invalid gate or edge mode")
    q=params.get("q") or DEFAULT_Q
    episode=db.execute("SELECT question,seed,prefix FROM episodes WHERE q=?",(q,)).fetchone()
    if episode is None:raise ValueError("Unknown example")
    arg=params.get("suppress","")
    if arg and (len(arg)>12 or not arg.isascii() or not arg.isdecimal()):raise ValueError("Invalid edge ID")
    omit=int(arg) if arg else -1
    ranked=[dict(row) for row in db.execute(RANK,dict(q=q,limit=GATES[gate],mode=mode,omit=omit))]
    edges=[dict(id=r["id"],title=r["title"],anchor=r["anchor"]) for r in ranked if r["edge"]]
    if arg and omit not in {r["id"] for r in edges}:raise ValueError("This address has no edge in the selected mode")
    best=ranked[0]
    route=("question","href" if mode=="href" else "literal","directory")[best["tier"]]
    return dict(q=q,gate=gate,mode=mode,suppress=None if omit<0 else omit,**dict(episode),selected=best,route=route,witness=witness(best,route,episode),
                eligible_counts=dict(projected=len(ranked),question=sum(r["direct"] for r in ranked),
                                     links=sum(r["edge"] and r["id"]!=omit for r in ranked)),
                edges=edges,ranked=ranked,directory_size=5989847)

def grading(row):
    # This is the only endpoint that opens annotations. Recompute the selection before grading it.
    answer=json.loads((ROOT/"audit.json").read_text(encoding="utf8"))[row["q"]]
    gate,mode=row["gate"],row["mode"]
    if gate=="off":arm={"href":"href_first","literal":"text_first","none":"free"}[mode]
    else:
        arm={"0":"two_words","59":"primary","5989":"loose"}[gate]+"_"+{"href":"href","literal":"text","none":"free"}[mode]
    gold=set(answer["support"]);sel=normalize(row["selected"]["title"]);first=normalize(row["seed"])
    hit=sorted({first,sel}&gold)
    return dict(q=row["q"],gate=gate,mode=mode,suppress=row["suppress"],support=sorted(gold),
                selected_match=sel in gold,matching_titles=hit,exact_support=len(hit)==len(gold),
                support_recall=len(hit)/len(gold),expected_id=answer["expected"][arm] if row["suppress"] is None else None,
                original_arm=arm,selected_id=row["selected"]["id"])

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        url=urlsplit(self.path)
        if url.path=="/":self.reply(200,"text/html; charset=utf-8",(ROOT/"index.html").read_bytes());return
        if url.path not in ("/api/cases","/api/select","/api/audit"):
            self.reply(404,"text/plain",b"Unknown route");return
        try:
            data=parse_qs(url.query,keep_blank_values=True,max_num_fields=8)
            if any(len(v)!=1 for v in data.values()):raise ValueError("Repeated control")
            params={k:v[0] for k,v in data.items()}
            with closing(sqlite3.connect((ROOT/"directory.sqlite").as_uri()+"?mode=ro",uri=True)) as db:
                db.row_factory=sqlite3.Row
                if url.path=="/api/cases":
                    if params:raise ValueError("No controls on case index")
                    blob=cases(db)
                else:
                    blob=selection(db,params)
                    if url.path=="/api/audit":blob=grading(blob)
            status=200
        except ValueError as exc:
            status=400;blob=dict(error=str(exc))
        self.reply(status,"application/json; charset=utf-8",json.dumps(blob,ensure_ascii=False,allow_nan=False).encode("utf8"))
    def reply(self,status,mime,body):
        self.send_response(status);self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store")
        self.end_headers();self.wfile.write(body)

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port",type=int,default=0)
    args=ap.parse_args()
    with ThreadingHTTPServer(("127.0.0.1",args.port),Handler) as srv:
        print(f"http://127.0.0.1:{srv.server_port}/",flush=True)
        try:srv.serve_forever()
        except KeyboardInterrupt:pass

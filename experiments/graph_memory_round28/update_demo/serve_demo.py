"""Local interactive inspector for citations and physical evidence changes."""
import argparse
import functools
import gzip
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
QUERY = """SELECT * FROM (
 SELECT * FROM (SELECT score,ord,lo,hi FROM pre WHERE q=? AND bound<=? ORDER BY bound DESC LIMIT 1)
 UNION ALL
 SELECT * FROM (SELECT score,ord,lo,hi FROM suf WHERE q=? AND bound>=? ORDER BY bound ASC LIMIT 1)
) ORDER BY score DESC,ord LIMIT 1"""
def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix==".gz" else data)
class Inspector:
    def __init__(self, corpus=None):
        self.cases=read(ROOT.parent/"revoked_evidence/decisions.json.gz")
        self.order=read(ROOT.parent/"retraction_db/plan.json")["qids"]
        self.ids={q:i for i,q in enumerate(self.order)}
        self.sources={};self.questions={};self.references={}
        if corpus:
            for article in read(corpus)["data"]:
                self.sources[article["title"]]="\n\n".join(p["context"] for p in article["paragraphs"])
                for p in article["paragraphs"]:
                    self.questions.update({q["id"]:q["question"] for q in p["qas"] if q["id"] in self.ids})
                    self.references.update({q["id"]:list(dict.fromkeys(a["text"] for a in q["answers"])) for q in p["qas"] if q["id"] in self.ids})
            if set(self.order)!=set(self.questions):raise ValueError("Missing benchmark questions in corpus")
    def answer(self,article,row):
        if row is None:return None
        score,_,a,b=row
        text=self.sources.get(article)
        return {"range":[a,b],"score":round(score,4),"text":text[a:b] if text is not None else None}
    def listing(self):
        return [{"q":q,"article":self.cases[q]["article"],"question":self.questions.get(q),"diff":not self.cases[q]["same_source"]} for q in self.order]
    def inspect(self,q,l=None,h=None):
        if q not in self.ids:raise ValueError("Unknown question")
        case=self.cases[q];default=case["projections"]["record"]["cut"];article=case["article"]
        if l is None and h is None:l,h=default
        if not(isinstance(l,int) and isinstance(h,int) and 0<=l<h<=2**31-1):raise ValueError("Expected 0 <= start < end <= 2147483647")
        i=self.ids[q]
        uri=(ROOT/"sky.sqlite").as_uri()+"?mode=ro&immutable=1"
        import contextlib
        with contextlib.closing(sqlite3.connect(uri,uri=True)) as db:
            found=db.execute(QUERY,(i,l,i,h)).fetchone()
        return {"article":article,"q":q,"question":self.questions.get(q),"cut":[l,h],
                "references":self.references.get(q,[]),"presets":{k:v["cut"] for k,v in case["projections"].items()},
                "base":self.answer(article,case["answers"]["base"]),"fixed":self.answer(article,found),
                "physical":self.answer(article,case["answers"]["retract"]) if [l,h]==default else None,
                "physically_measured":[l,h]==default,"candidates":case["candidates"],"bytes":case["state_bytes"]}
class Handler(BaseHTTPRequestHandler):
    def __init__(self,*args,inspector,**kw):
        self.inspector=inspector
        super().__init__(*args,**kw)
    def do_GET(self):
        url=urlsplit(self.path);params=parse_qs(url.query)
        if url.path=="/":
            result=(ROOT/"index.html").read_bytes();kind="text/html";status=200
        else:
            kind="application/json";status=200
            try:
                if url.path=="/api/cases":payload=self.inspector.listing()
                elif url.path=="/api/read":
                    start,end=(int(params[k][0]) if k in params else None for k in ("start","end"))
                    payload=self.inspector.inspect(params.get("q",[""])[0],start,end)
                else:payload={"error":"Unknown endpoint"};status=404
            except (ValueError,KeyError) as exc:payload={"error":str(exc)};status=400
            result=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status);self.send_header("Content-Type",kind+"; charset=utf-8")
        self.send_header("Content-Length",str(len(result)));self.end_headers();self.wfile.write(result)
    def log_message(self,*args):pass

def server(port,corpus=None):
    return ThreadingHTTPServer(("127.0.0.1",port),functools.partial(Handler,inspector=Inspector(corpus)))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8079);p.add_argument("--corpus",type=Path)
    args=p.parse_args();fallback=Path("D:/CodexResearch/x20-r25-squad/dev-v1.1.json")
    selected=args.corpus or (fallback if fallback.is_file() else None)
    with server(args.port,selected) as app:
        print(f"http://127.0.0.1:{app.server_port}/",flush=True);app.serve_forever()

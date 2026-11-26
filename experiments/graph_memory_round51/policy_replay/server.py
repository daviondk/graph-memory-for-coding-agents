"""Local interface for comparing graph-reading policies at a frozen reader snapshot."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

import replay
import rank_view

ROOT=Path(__file__).resolve().parent

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def send(self,status,mime,data):
        self.send_response(status)
        self.send_header("Content-Type",mime+"; charset=utf-8")
        self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route=urlsplit(self.path)
        if route.path in ("/","/rank"):
            filename="rank.html" if route.path=="/rank" else "index.html"
            self.send(200,"text/html",(ROOT/filename).read_bytes())
            return
        if route.path not in ("/api/compare","/api/rank/cases","/api/rank/query"):
            self.send_error(404)
            return
        args=parse_qs(route.query,keep_blank_values=True)
        def param(k,default):
            return args.get(k,[default])[0]
        panel=param("panel","gate_confirmation")
        try:
            if route.path.startswith("/api/rank/"):
                result=rank_view.get_result(route.path,{k:v[0] for k,v in args.items()})
                self.send(200,"application/json",json.dumps(result,ensure_ascii=False,allow_nan=False).encode())
                return
            if panel not in replay.PANELS:
                raise ValueError("Unknown panel")
            uri=(ROOT/"replay.sqlite").as_uri()+"?mode=ro&immutable=1"
            with closing(sqlite3.connect(uri,uri=True)) as db:
                result,rows=replay.evaluate(db,panel,param("start","dense"),param("end","registered"))
                examples=[]
                for q,a,b,em,f1 in sorted(rows,key=lambda r:(-abs(r[4]),r[0])):
                    label=db.execute("SELECT label FROM questions WHERE panel=? AND question=?",(panel,q)).fetchone()
                    examples.append(dict(id=q,title=label[0] if label else q,prompt_before=a,prompt_after=b,
                                         em_change=em,f1_change=f1))
                result["examples"]=examples
            self.send(200,"application/json",json.dumps(result,ensure_ascii=False,allow_nan=False).encode())
        except (ValueError,OverflowError) as exc:
            self.send(400,"application/json",json.dumps({"error":str(exc)}).encode())

if __name__=="__main__":
    opts=argparse.ArgumentParser()
    opts.add_argument("--port",type=int,default=0)
    with ThreadingHTTPServer(("127.0.0.1",opts.parse_args().port),Handler) as http:
        print(f"http://127.0.0.1:{http.server_port}",flush=True)
        http.serve_forever()


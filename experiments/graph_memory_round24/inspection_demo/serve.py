"""Serve only the fixed replay routes on the loopback interface."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from urllib.parse import parse_qs,urlsplit
from store import ROOT,connect,cases,view

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed=urlsplit(self.path)
        try:
            if parsed.path=="/":
                data=(ROOT/"index.html").read_bytes();kind="text/html; charset=utf-8"
            elif parsed.path in ("/api/cases","/api/view"):
                with closing(connect()) as db:
                    if parsed.path=="/api/cases":obj=cases(db)
                    else:
                        query=parse_qs(parsed.query)
                        if set(query)!={"case","format","policy"} or any(len(v)!=1 for v in query.values()):raise ValueError
                        obj=view(db,*[query[k][0] for k in ("case","format","policy")])
                data=json.dumps(obj,separators=(",",":"),ensure_ascii=False).encode();kind="application/json; charset=utf-8"
            else:self.send_error(404);return
        except (ValueError,KeyError,IndexError):
            self.send_error(400,"Unknown case, format or policy");return
        self.send_response(200);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8774)
    httpd=ThreadingHTTPServer(("127.0.0.1",p.parse_args().port),Handler)
    print(f"http://127.0.0.1:{httpd.server_port}/",flush=True)
    try:httpd.serve_forever()
    except KeyboardInterrupt:pass
    finally:httpd.server_close()

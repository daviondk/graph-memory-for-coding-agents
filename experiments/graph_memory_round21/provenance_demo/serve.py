"""Run the local ICDE provenance explorer with the Python standard library."""
import argparse
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from urllib.parse import parse_qs, urlsplit
from store import DATA,connect,view,revisions


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url=urlsplit(self.path)
        try:
            query=parse_qs(url.query)
            if url.path=="/":
                content=DATA.with_name("index.html").read_bytes();kind="text/html; charset=utf-8"
            else:
                with contextlib.closing(connect()) as db:
                    if url.path=="/api/cases":
                        data=[{"t":t,"steps":s} for t,s in db.execute("SELECT t,steps FROM trace ORDER BY t")]
                    elif url.path=="/api/view":
                        data=view(db,query["t"][0],int(query["step"][0]))
                    elif url.path=="/api/edge":
                        data=revisions(db,query["t"][0],int(query["a"][0]),int(query["b"][0]),int(query["step"][0]))
                    else:
                        self.send_error(404);return
                content=json.dumps(data,separators=(",",":")).encode();kind="application/json"
        except (KeyError,ValueError,IndexError):
            self.send_error(400,"Invalid history or event");return
        self.send_response(200);self.send_header("Content-Type",kind);self.send_header("Content-Length",str(len(content)))
        self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(content)

    def log_message(self,fmt,*args):
        pass


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8765)
    args=parser.parse_args()
    if not DATA.is_file():sys.exit("The snapshot provenance.sqlite must be beside serve.py")
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"http://127.0.0.1:{server.server_port}/",flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

"""Serve both reviewed interactive SQLite views locally. Ctrl+C stops all three servers."""
import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import sys

D=Path(__file__).resolve().parent

def verify_assets():
    for relative,digest in json.loads((D/"app-inputs.json").read_bytes()).items():
        if sha256((D/relative).read_bytes()).hexdigest()!=digest:
            raise ValueError(f"Unexpected runtime file: {relative}")

@contextmanager
def child(entry):
    proc=subprocess.Popen([sys.executable,"-B","-u",str(entry),"--port","0"],stdout=subprocess.PIPE,text=True)
    try:
        url=proc.stdout.readline().strip()
        if not url.startswith("http://127.0.0.1:") or not url.rsplit(":",1)[-1].isdigit():
            raise RuntimeError("The demonstration server did not start")
        yield url
    finally:
        if proc.poll() is None:proc.terminate()
        proc.wait(timeout=10)

class Landing(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=="/sessions.json":
            data=json.dumps(self.server.scenes).encode()
            kind="application/json"
        elif self.path=="/":
            content=(D/"start.html").read_text(encoding="utf8")
            for name,url in self.server.scenes.items():content=content.replace("{{"+name+"}}",url)
            data=content.encode()
            kind="text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type",kind)
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def log_message(self,*args): pass

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--port",type=int,default=8784)
    args=cli.parse_args()
    verify_assets()
    with ExitStack() as stack:
        server=stack.enter_context(HTTPServer(("127.0.0.1",args.port),Landing))
        server.scenes={name:stack.enter_context(child(D/"apps"/name/script)) for name,script in
                       (("trace","launcher.py"),("code","app.py"))}
        print(f"http://127.0.0.1:{server.server_port}",flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass


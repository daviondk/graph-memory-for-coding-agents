"""Serve the eleven interactive SQLite consoles locally. Ctrl+C stops the local servers."""
import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

D=Path(__file__).resolve().parent

def verify_assets():
    for relative,digest in json.loads((D/"app-inputs.json").read_bytes()).items():
        if sha256((D/relative).read_bytes()).hexdigest()!=digest:
            raise ValueError(f"Unexpected runtime file: {relative}")

@contextmanager
def child(entry):
    proc=subprocess.Popen([sys.executable,"-B","-u",str(entry),"--port","0"],stdout=subprocess.PIPE,text=True)
    try:
        url = urlsplit(proc.stdout.readline().strip())
        if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
                or url.path not in ("", "/") or url.query or url.fragment):
            raise RuntimeError(f"The demonstration server did not start: {entry.name}")
        yield f"http://127.0.0.1:{url.port}"
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

APPS = {
    "churn": "demo/server.py", "trace": "launcher.py", "code": "app.py", "context": "server.py",
    "flow": "server.py", "stream": "server.py", "core": "core_view.py",
    "address": "address_server.py", "policies":"server.py", "history":"extension.py", "directory":"serve.py",
}

@contextmanager
def application(port):
    verify_assets()
    with ExitStack() as stack:
        server = stack.enter_context(HTTPServer(("127.0.0.1", port), Landing))
        server.scenes = {
            name: stack.enter_context(child(D/"apps"/name/entry))
            for name, entry in APPS.items()
        }
        yield server

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--port", type=int, default=8784)
    with application(cli.parse_args().port) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

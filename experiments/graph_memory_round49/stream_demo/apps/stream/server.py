"""Loopback HTTP console with independent in-memory state per visitor."""
import argparse
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from uuid import uuid4
from urllib.parse import urlsplit
from engine import D, History, Reader, verify_from_rows

class Console(BaseHTTPRequestHandler):
    def send(self, code, body, mime):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path != "/":
            self.send_error(404)
            return
        self.send(200, (D/"index.html").read_bytes(), "text/html; charset=utf-8")

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0<size<=2048 or self.path!="/api":
                raise ValueError("Invalid request")
            data = json.loads(self.rfile.read(size))
            action = data["action"]
            sessions = self.server.sessions
            if action == "open":
                spacing = int(data.get("spacing",16))
                if spacing not in (0,4,16,64):
                    raise ValueError("Unknown checkpoint spacing")
                key = uuid4().hex
                reader = Reader(History(data.get("trace","Medium")),spacing)
                sessions[key] = reader
                if len(sessions)>20:
                    sessions.popitem(last=False)
                reader.advance(1)
            else:
                key = data["session"]
                reader = sessions[key]
                sessions.move_to_end(key)
                if action == "advance":
                    distance = int(data["distance"])
                    if distance not in (1,4,1000):
                        raise ValueError("Invalid advance")
                    reader.advance(min(reader.history.steps,reader.step+distance))
                elif action != "audit":
                    raise ValueError("Unknown action")
            result = dict(reader.last,session=key)
            if action == "audit":
                independent = verify_from_rows(reader.history, reader.step)
                result["verified"] = independent==reader.last["ids"]
            self.send(200,json.dumps(result).encode(),"application/json")
        except (KeyError, ValueError, TypeError) as error:
            self.send(400,json.dumps({"error":str(error)}).encode(),"application/json")
    def log_message(self,*args):
        pass

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=0)
    with HTTPServer(("127.0.0.1",parser.parse_args().port), Console) as server:
        server.sessions=OrderedDict()
        print(f"http://127.0.0.1:{server.server_port}",flush=True)
        server.serve_forever()

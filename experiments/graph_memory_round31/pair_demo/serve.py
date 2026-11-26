"""Deliver ranked pairs from SQLite and keep the live client free of stored rankings."""
import argparse
import contextlib
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import combinations
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent


def winner(edges, removed):
    return next((e for e in edges if e >> 4 not in removed and (e & 15) not in removed), None)


def decide(tree, raw, n, removed, load_full):
    result = {"winner": None, "certificate": None, "tree_fallback": False,
              "raw_fallback": False, "empty": n - len(removed) < 2}
    if result["empty"]:
        return result

    withdrawn = sorted(removed)
    if len(removed) <= 2:
        result["certificate"] = withdrawn
        result["winner"] = winner(tree, removed)
    else:
        for size in range(3):
            for subset in combinations(withdrawn, size):
                candidate = winner(tree, subset)
                if candidate is None or winner([candidate], removed) is not None:
                    result["certificate"] = list(subset)
                    result["winner"] = candidate
                    break
            if result["certificate"] is not None:
                break
        if result["certificate"] is None:
            result["winner"] = winner(load_full(), removed)
            result["tree_fallback"] = True

    ordinary = winner(raw, removed)
    if ordinary is None:
        ordinary = winner(load_full(), removed)
        result["raw_fallback"] = True
    assert ordinary == result["winner"]
    return result


def query(q, withdrawn):
    uri = (HERE/"evidence.sqlite").as_uri() + "?mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        row = db.execute("select n,tree,raw from pairs where q=?", (q,)).fetchone()
        if row is None:
            raise ValueError("Unknown question")
        n, tree, raw = row
        if len(set(withdrawn)) != len(withdrawn) or any(type(i) != int or not 0 <= i < n for i in withdrawn):
            raise ValueError("Invalid source set")

        def load_full():
            return db.execute("select full from pairs where q=?", (q,)).fetchone()[0]

        return decide(tree, raw, n, set(withdrawn), load_full)


def saved_lists(q):
    uri = (HERE/"evidence.sqlite").as_uri() + "?mode=ro&immutable=1"
    with contextlib.closing(sqlite3.connect(uri, uri=True)) as db:
        record = db.execute("select raw,tree from pairs where q=?", (q,)).fetchone()
    if record is None:
        raise ValueError("Unknown question")
    return {"raw": list(record[0]), "tree": list(record[1])}


def live_page():
    panel = json.loads((HERE/"cases.json").read_bytes())
    for case in panel["questions"]:
        for name in ("full", "tree", "raw"):
            case[name + "_count"] = len(case.pop(name))
    payload = json.dumps(panel, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return (HERE/"viewer.html").read_text(encoding="utf8").replace("/*__CASES__*/null", payload).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        status = 200
        if url.path == "/":
            body, kind = self.server.page, "text/html"
        elif url.path in ("/api/query", "/api/lists"):
            kind = "application/json"
            try:
                fields = parse_qs(url.query)
                withdrawn = [int(i) for i in fields.get("lost", [""])[0].split(",") if i]
                q = fields.get("q", [""])[0]
                result = saved_lists(q) if url.path == "/api/lists" else query(q, withdrawn)
                body = json.dumps(result).encode()
            except ValueError as error:
                body, status = json.dumps({"error": str(error)}).encode(), 400
        else:
            body, status, kind = b"Not found", 404, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def make_server(port):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.page = live_page()
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8086)
    with make_server(parser.parse_args().port) as server:
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()

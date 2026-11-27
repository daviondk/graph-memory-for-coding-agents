"""Serve a queryable local SQLite replay, or export its self-contained browser view."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from demo_store import CASES, HERE, build, inspect, read, world


def connect(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def snapshot(db):
    data = {case: inspect(db, case) for case in CASES}
    data["worlds"] = []
    for s in range(16):
        rows = db.execute("SELECT c FROM synthetic WHERE shift=? ORDER BY a,b", (s,))
        data["worlds"].append([c for c, in rows])
    data["projection"] = world(db,0,0,0)["projection"]
    return data


def html(data):
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    return (HERE / "view.html").read_text(encoding="utf8").replace("__DATA__",raw).encode("utf8")


def checked(db, data):
    logs = read(HERE / "new-queries.json.gz")
    streams = read(HERE / "events.json.gz")
    for case, (repo, rev) in CASES.items():
        value = data[case]
        row = next(r for r in logs[repo] if r["sha"] == rev)
        seen = {}
        for _, paths in streams[repo][:row["t"]]:
            for f in paths if len(paths) <= 64 else ():
                seen.setdefault(f,len(seen))
        for mode, files in value["ranks"].items():
            assert [seen[f] for f in files] == row["ranks"][mode]
            assert len(set(files) & set(value["gold"])) == row["hits"][mode]
    for s in range(16):
        for a in range(16):
            for b in range(16):
                answer = world(db,s,a,b)
                assert answer["third"] == (a+b+s)%16 == data["worlds"][s][a*16+b]
                assert answer["projection"] == data["projection"] == [2]*16


def handler(db_path, page):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            parts = path.strip("/").split("/")
            if path == "/":
                body, media = page, "text/html; charset=utf-8"
            else:
                with closing(connect(db_path)) as db:
                    if len(parts) == 2 and parts[0]=="case" and parts[1] in CASES:
                        result = inspect(db,parts[1])
                    elif (len(parts)==4 and parts[0]=="world" and
                          all(k in {str(i) for i in range(16)} for k in parts[1:])):
                        result = world(db,*map(int,parts[1:]))
                    else:
                        self.send_error(404)
                        return
                    body, media = json.dumps(result).encode(), "application/json"
            self.send_response(200)
            self.send_header("Content-Type",media)
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            return
    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("export","verify","serve"))
    p.add_argument("--port", type=int, default=8657)
    args = p.parse_args()
    with TemporaryDirectory(dir=HERE) as folder:
        db_path = Path(folder) / "memory.sqlite"
        build(db_path)
        with closing(connect(db_path)) as db:
            data = snapshot(db)
            checked(db,data)
        page = html(data)
        dest = HERE / "demo.html"
        if args.mode == "export":
            dest.write_bytes(page)
        elif args.mode == "verify":
            assert dest.read_bytes() == page
        else:
            with ThreadingHTTPServer(("127.0.0.1",args.port), handler(db_path,page)) as server:
                print(f"Open http://127.0.0.1:{server.server_port}/?source=sqlite",flush=True)
                server.serve_forever()
        print("Two real gold-separated SQL replays and 4,096 synthetic outcomes verified.")


if __name__ == "__main__":
    main()

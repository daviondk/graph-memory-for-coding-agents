"""Replay a recorded graph-memory query against its bundled immutable SQLite prefix."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from itertools import accumulate
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent


def number(raw, start):
    value = 0
    for at in range(start, len(raw)):
        b = raw[at]
        value |= (b & 127) << (7*(at-start))
        if b < 128:
            return value, at+1
    raise ValueError("incomplete integer")


def members(raw):
    values = []
    at = 0
    while at < len(raw):
        value, at = number(raw, at)
        values.append(value)
    return values


def exception_packet(raw):
    if not raw or raw[0] != 6:
        raise ValueError("expected count plus exceptions")
    n, at = number(raw, 1)
    if at == len(raw):
        return n, []
    encoding = raw[at]
    if encoding == 0:
        ids = members(raw[at+1:])
    elif encoding == 1:
        ids = [x-1 for x in accumulate(v+1 for v in members(raw[at+1:]))]
    elif encoding == 2:
        first, start = number(raw, at+1)
        ids = [first+i*8+b for i,v in enumerate(raw[start:]) for b in range(8) if v & (1<<b)]
    else:
        raise ValueError("unknown exception encoding")
    assert len(ids) == len(set(ids))
    return n, ids


def replay(mode):
    q = json.loads((HERE/"query.json").read_bytes())
    f = q["anchor"]
    state = q["states"][mode]
    tie = {int(k):v for k,v in q["tie"].items()}
    hot = {int(k):bytes.fromhex(v) for k,v in q["hot_incident"].items()}
    present = hot.copy()
    for key, blob in state["event_blobs"].items():
        body = bytes.fromhex(blob)
        if f in members(body):
            j = int(key)
            assert j not in present or present[j] == body
            present[j] = body
    n, exceptions = exception_packet(bytes.fromhex(state["packet"]))
    covered = set(present).union(exceptions)
    certified = len(covered) == n
    assert len(covered) <= n
    uri = (HERE/"source.sqlite").as_uri() + "?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        ledger = dict(posting_calls=0, posting_bytes=0, body_calls=0, body_bytes=0)
        selects = []
        db.set_trace_callback(selects.append)
        if certified:
            ids = covered
        else:
            blob, = db.execute("SELECT js FROM posting WHERE f=?", (f,)).fetchone()
            ids = set(members(blob))
            ledger.update(posting_calls=1, posting_bytes=len(blob))
        assert len(ids) == n and set(present) <= ids
        missing = sorted(ids-present.keys())
        bodies = list(present.values())
        if missing:
            marks = ",".join("?" for _ in missing)
            rows = db.execute("SELECT members FROM event WHERE j IN ("+marks+") ORDER BY j", missing).fetchall()
            assert len(rows) == len(missing)
            for (blob,) in rows:
                assert f in members(blob)
                bodies.append(blob)
            ledger.update(body_calls=1, body_bytes=sum(len(row[0]) for row in rows))
        db.set_trace_callback(None)
        counts = Counter(i for b in bodies for i in members(b) if i != f)
        ranking = sorted(counts, key=lambda i:(-counts[i],-tie[i],i))[:8]
        for i in q["prior"]:
            if len(ranking) == 8:
                break
            if i != f and i not in ranking:
                ranking.append(i)
        found = [[i,counts[i]] for i in ranking]
        # Separate audit connection work is excluded from the visitor query's ledger.
        all_rows = db.execute("SELECT j,rev,members FROM event ORDER BY j").fetchall()
        assert len(all_rows) == q["prefix"]
        oracle = Counter()
        source = {}
        archive_ids = set()
        for j,rev,blob in all_rows:
            all_files = members(blob)
            if f in all_files:
                archive_ids.add(j)
                oracle.update(all_files)
            if j in missing:
                source[j] = rev.hex()
        oracle_rank = sorted((i for i in tie if i != f), key=lambda i:(-oracle[i],-tie[i],i))[:8]
        assert ids == archive_ids and found == [[i,oracle[i]] for i in oracle_rank] == q["expected"]
        assert ledger == state["recorded_reads"] and len(selects) == ledger["posting_calls"]+ledger["body_calls"]
    paths = q["paths"]
    return dict(mode=mode, project=q["project"], file=paths[str(f)], request=q["query"], prefix=q["prefix"],
                count=n, resident=len(present), exceptions=exceptions, certified=certified, read=ledger,
                missing=missing, source_commits=source, statements=selects, full_history_verified=True,
                ranking=[[paths[str(i)],score] for i,score in found])


def serve(port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            routes = {"/query/notify":"notify", "/query/quiet":"quiet"}
            if self.path == "/":
                content = (HERE/"snapshot.html").read_bytes()
                kind = "text/html; charset=utf-8"
            elif self.path in routes:
                content = json.dumps(replay(routes[self.path])).encode("utf-8")
                kind = "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    with HTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="use recorded state of the notifications-off policy")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--serve", action="store_true", help="serve the two queries on localhost")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.serve:
        serve(args.port)
        raise SystemExit(0)
    result = replay("quiet" if args.quiet else "notify")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"{result['project']} | request {result['request']} | {result['file']}")
        print(f"Resident {result['resident']} of {result['count']}. Exceptions {result['exceptions']}. Certified {result['certified']}.")
        for stmt in result["statements"]:
            print(stmt)
        print("SQLite payload", sum(result["read"][name] for name in ("posting_bytes","body_bytes")), "bytes")
        for j,rev in result["source_commits"].items():
            print("Event", j, rev)
        print("Eight file scores, verified against a separate scan of the full history")
        for name,score in result["ranking"]:
            print(f"{score:3}  {name}")

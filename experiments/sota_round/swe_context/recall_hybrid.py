"""Run Recall's native Linux index and search against an isolated CPU Ollama."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
import threading
import time


@contextmanager
def ollama_transport(destination, stats, checkpoint):
    """Relay unchanged HTTP bodies to the Windows loopback through WSL interop."""
    class Relay(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/api/embed":
                self.send_error(404)
                return
            payload = self.rfile.read(int(self.headers["Content-Length"]))
            request = json.loads(payload)
            started = time.monotonic()
            target = checkpoint / (hashlib.sha256(payload).hexdigest() + ".json")
            cached = target.is_file()
            if cached:
                body = target.read_bytes()
            else:
                response = subprocess.run(
                ["/mnt/c/Windows/system32/curl.exe", "--silent", "--show-error", "--fail", "--max-time", "290",
                 "--header", "Content-Type: application/json", "--data-binary", "@-", destination + self.path],
                input=payload, capture_output=True,
                )
                if response.returncode:
                    self.send_error(502, response.stderr.decode("utf-8", errors="replace")[:100])
                    return
                body = response.stdout
            parsed = json.loads(body)
            lengths = {len(v) for v in parsed["embeddings"]}
            assert len(parsed["embeddings"]) == len(request["input"]) and lengths == {768}
            if not cached:
                tmp = target.with_suffix(".part")
                tmp.write_bytes(body)
                tmp.replace(target)
            stats.append({"checkpoint": cached, "n": len(request["input"]), "chars": sum(map(len, request["input"])), "dim": 768,
                          "prompt_eval_count": parsed.get("prompt_eval_count"), "seconds": time.monotonic() - started})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Relay)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, required=True)
    ap.add_argument("--ollama", default="http://127.0.0.1:18842")
    args = ap.parse_args()
    out = Path(__file__).resolve().parent
    data = args.data.resolve()
    os.environ["RECALL_HOME"] = str(data / "recall-empty-home")
    os.environ["RECALL_MEMORY"] = str(data / "recall-empty-memory")
    sys.path.insert(0, str(args.upstream.resolve() / "src"))
    import numpy as np
    from recall import __version__, embeddings, evals_swecb as author
    from recall.chats import store
    assert __version__ == "0.5.0"
    tasks = {r["id"]: r for r in author._tasks(str(data / "recall-safe-queries"), "lite")}
    ids = json.loads((data / "recall-safe-queries" / "ordinals.json").read_text(encoding="utf-8"))
    assert len(tasks) == len(set(ids)) == len(ids) == 99 and set(tasks) == set(ids)
    stats, rows, sessions, keys = [], [], {}, {}
    utc = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    for path in sorted((data / "traces").glob("*.jsonl")):
        assert re.fullmatch(r"[0-9a-f]{8}", path.stem)
        session = author._transcript(str(path), "swecb")
        if session is not None:
            sessions[session.native_id] = session
            keys[session.native_id] = path.stem
    assert len(sessions) == 300
    checkpoint = data / "recall-embedding-checkpoints"
    checkpoint.mkdir(exist_ok=True)
    with ollama_transport(args.ollama, stats, checkpoint) as base:
        embedder = embeddings.Embedder({"provider": "ollama", "name": "nomic-embed-text", "base_url": base})
        # The published harness shares this cache across runs. Start with an
        # empty in-memory cache to measure the cost of building all 600 vectors.
        with sqlite3.connect(":memory:") as cache:
            con = author._index(list(sessions.values()), embedder=embedder, cache=cache)
        msg_count, = con.execute("select count(*) from messages").fetchone()
        vectors, dim, = con.execute("select count(*), min(length(vec))/2 from vectors").fetchone()
        assert msg_count == vectors == 600 and dim == 768
        built = time.monotonic()
        print(f"Indexed {vectors} dimension-{dim} vectors in {built-start:.1f}s", flush=True)
        for ordinal, iid in enumerate(ids):
            q = author._query(tasks[iid], "problem")
            v = embeddings.query_vector(q, embedder)
            assert v is not None and len(v) == dim
            top = max(author.KS)
            own = f"{next(iter(sessions.values())).agent}:{iid}"
            ranked = [r["chat_id"] for r in store.search(con, q, limit=top + 1, vector=v) if r["chat_id"] != own][:top]
            opaque = [keys[k.split(":", 1)[1]] for k in ranked[:10]]
            assert len(set(opaque)) == len(opaque) == 10
            rows.append({"ordinal": ordinal, "recall_hybrid": opaque})
        con.close()
    search_seconds = time.monotonic() - built
    assert len(stats) == 118 and sum(r["n"] for r in stats) == 699
    path = out / "recall_hybrid.json"
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    result = {
        "started_utc": utc, "ended_utc": datetime.now(timezone.utc).isoformat(), "model": embedder.model,
        "ollama": "0.40.5", "data_and_model_registry": "staged with stage_recall_ollama.py",
        "recall_commit": "585d0e21553d20e353588b9278e067d641a8283a",
        "scope": "300 full-transcript inputs, 99 original unmasked issue texts, author-native in-memory index",
        "runtime": {"platform": platform.platform(), "python": platform.python_version(),
                    "numpy": np.__version__, "sqlite": sqlite3.sqlite_version},
        "messages": msg_count, "queries": len(rows), "vector_dim": dim, "has_gold_access": False,
        "index_seconds": built - start, "search_seconds": search_seconds,
        "http_call_count": len(stats), "http_inputs": sum(r["n"] for r in stats),
        "http_evaluated_tokens": sum(r["prompt_eval_count"] or 0 for r in stats), "calls": stats,
        "sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                   for f in (path, Path(__file__), out / "source.json", out / "recall_keyword_pin.json")},
    }
    (out / "recall_hybrid_pin.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Locked {len(rows)} rankings {result['sha256'][path.name]}", flush=True)


if __name__ == "__main__":
    main()

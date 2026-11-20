import datetime as dt
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:18884"


def ask(route, data=None):
    raw = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(BASE+route, data=raw, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


if __name__ == "__main__":
    receipts = json.loads((HERE / "selection_receipt.json").read_text())
    for f, digest in receipts["hashes"].items():
        assert hashlib.sha256((HERE/f).read_bytes()).hexdigest() == digest
    log = HERE / "responses.jsonl"
    completed = {(m["sha"],m["arm"]) for m in (json.loads(l) for l in log.read_text().splitlines())} if log.exists() else set()
    if not (HERE / "model.json").exists():
        (HERE / "model.json").write_text(json.dumps(ask("/v1/models"), indent=2),encoding="utf-8")
    requests = [json.loads(line) for line in (HERE/"requests.jsonl").read_text().splitlines()]
    with log.open("a", encoding="utf-8", newline="\n", buffering=1) as out:
        for row in requests:
            if (row["sha"],row["arm"]) in completed:
                continue
            start = time.monotonic()
            started = dt.datetime.now(dt.timezone.utc).isoformat()
            errors = []
            for attempt in range(3):
                try:
                    response = ask("/v1/chat/completions", row["request"])
                    break
                except (TimeoutError, urllib.error.URLError) as e:
                    errors.append(str(e))
                    if attempt == 2:
                        with (HERE/"failure.jsonl").open("a") as f:
                            f.write(json.dumps({"sha":row["sha"],"arm":row["arm"],"errors":errors})+"\n")
                        raise
                    time.sleep(1)
            saved = {k:v for k,v in row.items() if k != "request"}
            saved.update({"response":response, "utc_start":started,"seconds":time.monotonic()-start,
                          "request_sha256":hashlib.sha256(json.dumps(row["request"]).encode()).hexdigest(), "http_errors":errors})
            out.write(json.dumps(saved)+"\n")
    print("requests completed",len(requests))

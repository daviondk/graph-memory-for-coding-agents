"""Run the unmodified Recall retriever without its outcome-aware evaluation loop."""
import argparse
import hashlib
import json
import os
import platform
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.json as paj
import pyarrow.parquet as pq


PIN = "585d0e21553d20e353588b9278e067d641a8283a"
OUTPUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    data = args.data.resolve()
    safe = data / "recall-safe-queries"
    os.environ["RECALL_HOME"] = str(data / "recall-empty-home")
    os.environ["RECALL_MEMORY"] = str(data / "recall-empty-memory")
    sys.path.insert(0, str(upstream / "src"))
    from recall import __version__, evals_swecb as author
    from recall.chats import store
    if __version__ != "0.5.0":
        raise RuntimeError("The pinned source must expose Recall 0.5.0")
    start = time.monotonic()
    utc = datetime.now(timezone.utc).isoformat()

    # Project the original GitHub JSON before its native task reader opens it.
    # The only target fields actually read are the same three the author uses.
    schema = pa.schema([(v, pa.string()) for v in ("instance_id", "repo", "problem_statement")])
    read_options = paj.ParseOptions(explicit_schema=schema, unexpected_field_behavior="ignore", newlines_in_values=True)
    safe_cases = safe / "repo" / "cases" / author.TASKS["lite"]
    safe_cases.mkdir(parents=True, exist_ok=True)
    for path in sorted((data / "case_metadata").glob("*.json")):
        target, = paj.read_json(path, parse_options=read_options).to_pylist()
        (safe_cases / path.name).write_text(json.dumps(target, ensure_ascii=False), encoding="utf-8")
    tasks = {x["id"]: x for x in author._tasks(str(safe), "lite")}
    ids = pq.read_table(data / "SWEContextBench_Related_Lite.parquet", columns=["instance_id"]).column(0).to_pylist()
    assert len(tasks) == len(ids) == len(set(ids)) == 99 and set(tasks) == set(ids)

    # Identical sorted ingestion and last-file-wins native ID behavior to the
    # transcript branch of author.load. Retain only the opaque filename outside.
    sessions = {}
    files = {}
    traces = sorted((data / "traces").glob("*.jsonl"))
    for path in traces:
        assert re.fullmatch(r"[0-9a-f]{8}", path.stem)
        session = author._transcript(str(path), "swecb")
        if session is not None:
            sessions[session.native_id] = session
            files[session.native_id] = path.stem
    assert len(traces) == 300
    con = author._index(list(sessions.values()))
    index_seconds = time.monotonic() - start
    count, unique, char_budget = con.execute(
        "select count(*), count(distinct substr(text,1,2000)), sum(length(substr(text,1,2000))) from messages"
    ).fetchone()
    rows = []
    rank_start = time.monotonic()
    for ordinal, iid in enumerate(ids):
        query = author._query(tasks[iid], "problem")
        # Mirrors run_search() for scope=all, full problem, keyword search.
        top = max(author.KS)
        own = f"{next(iter(sessions.values())).agent}:{iid}"
        ranked = [row["chat_id"] for row in store.search(con, query, limit=top + 1, vector=False) if row["chat_id"] != own][:top]
        opaque = [files[value.split(":", 1)[1]] for value in ranked[:10]]
        assert len(set(opaque)) == len(opaque)
        rows.append({"ordinal": ordinal, "recall_keyword": opaque})
    con.close()
    destination = OUTPUT / "recall_keyword.json"
    destination.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "method": "alirng/recall 0.5.0, keyword, all-scope, top 10 exported",
        "pin": PIN, "started_utc": utc, "has_gold_access": False,
        "source_archive_sha256": "bb9d2ead4a91d4d1ed719744522b2ddb9bcf5e2023b51fe20dcfac7cf4ae9eb4",
        "queries": len(rows), "raw_files": len(traces), "native_sessions": len(sessions),
        "indexed_messages": count, "distinct_first_2000_chars": unique, "first_2000_chars_total": char_budget,
        "returned_count_distribution": {str(k): sum(len(row["recall_keyword"]) == k for row in rows)
                                        for k in sorted({len(row["recall_keyword"]) for row in rows})},
        "prepare_and_index_seconds": index_seconds, "search_seconds": time.monotonic() - rank_start,
        "python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "pyarrow": pa.__version__,
        "sha256": {x.name: digest(x) for x in [destination, Path(__file__), OUTPUT / "source.json"]},
    }
    (OUTPUT / "recall_keyword_pin.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()

"""Independently check projected rows and replacement certificates against pinned Parquet."""
from collections import Counter
import re
import pyarrow.parquet as pq
from verify import D, R37, digest, load, path_id
from pathlib import Path
import json


def normalized(absolute):
    for prefix in ("/testbed/", "/workspace/"):
        if absolute.startswith(prefix):
            return path_id(absolute[len(prefix):])
    raise ValueError("Unrecognized path prefix")


def check_view(obs, public_rows):
    assert obs["command"] == "view" and not obs["is_error"]
    text = "\n".join(x["text"] for x in obs["content"] if isinstance(x, dict) and isinstance(x.get("text"), str))
    lines, active = {}, False
    for line in text.splitlines():
        if "cat -n" in line and line.rstrip().endswith("on " + obs["path"] + ":"):
            active = True
            continue
        if not active:
            continue
        number, tab, payload = line.partition("\t")
        if not tab or not re.fullmatch(r" *[0-9]+", number):
            active = False
            continue
        if re.search(r"<response clipped>|<NOTE:|\\.\\.\\.truncated", payload, re.I):
            continue
        coord = int(number)
        assert coord not in lines or lines[coord] == payload
        lines[coord] = payload
    expected = [[n, path_id(txt), len(txt.encode()), int(n+1 in lines)] for n, txt in sorted(lines.items())]
    assert expected == public_rows


def check_pair(act, obs, label):
    cmd, receipt = act["action"], obs["observation"]
    assert cmd["command"] == receipt["command"] == "str_replace" and not receipt["is_error"]
    assert cmd["path"] == receipt["path"] and normalized(cmd["path"]) == label["path"]
    assert act["id"] == obs["action_id"] and act.get("tool_call_id") == obs.get("tool_call_id")
    old, new, before, after = cmd["old_str"], cmd["new_str"], receipt["old_content"], receipt["new_content"]
    assert label["reason"] == "ok" and old.strip()
    start = before.index(old)
    end = start + len(old)
    assert before.find(old, start + 1) < 0 and before.replace(old, new, 1) == after
    assert not any(c in before for c in "\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")
    atoms, offset = [], 0
    for n, line in enumerate(before.split("\n"), 1):
        line_end = offset + len(line)
        if offset < end and start < line_end + int(line_end < len(before)):
            atoms.append([n, path_id(line), int(start <= line_end < end and line_end < len(before))])
        offset = line_end + 1
        if offset >= end:
            break
    assert atoms == label["atoms"] and len(old.encode()) == label["old_bytes"]
    assert label["partial_start"] == (start > 0 and before[start-1] != "\n")
    assert label["partial_end"] == (end < len(before) and before[end] != "\n" and old[-1] != "\n")
    assert label["leading_or_trailing_eol"] == (old[0] == "\n" or old[-1] == "\n")
    return old == new, "".join(old.split()) == "".join(new.split())


def main():
    original = Path("D:/CodexResearch/x20-r31-handoff")
    seal = load(D/"input-seal.json")
    assert digest(original/"files.json") == seal["source_manifest"]
    files = load(original/"files.json")["events"]
    assert len(files) == seal["shards"]
    schedule, views, labels = [load(D/n) for n in ("schedule.json.gz", "visible.json.gz", "sealed-targets.json.gz")]
    native = load(R37/"edit_demand/native_boundaries.json.gz")
    queries = {}
    for rid, meta in schedule.items():
        q = queries[rid] = {}
        end = {at: till for at, till, cmd, path in native[rid]["successful_writes"] if cmd == "str_replace"}
        for e in meta["events"]:
            if e[1] == "view":
                q[e[0]] = ("view", e[0], e[2])
            elif e[1] == "snapshot+invalidate":
                assert e[0] not in q and end[e[0]] not in q
                q[e[0]] = ("action", e[0], e[2])
                q[end[e[0]]] = ("receipt", e[0], e[2])
    counts, pending, lookup, whitespace_only, noops = Counter(), {}, {}, [], []
    for ref in files:
        shard = original / ref["file"]
        assert digest(shard) == ref["sha"]
        for batch in pq.ParquetFile(shard).iter_batches(columns=["run_id","event_index","event_json"], batch_size=384):
            runs, positions = batch.column(0).to_pylist(), batch.column(1).to_pylist()
            for j, (run, at) in enumerate(zip(runs, positions)):
                if run not in lookup:
                    lookup[run] = path_id(run)
                rid = lookup[run]
                if rid not in queries or at not in queries[rid]:
                    continue
                kind, action_index, path = queries[rid].pop(at)
                raw = json.loads(batch.column(2)[j].as_py())["raw"]
                counts[kind] += 1
                if kind == "view":
                    assert normalized(raw["observation"]["path"]) == path
                    public = views[rid][str(at)]
                    check_view(raw["observation"], public)
                    counts["numbered_rows_checked"] += len(public)
                    continue
                key = rid, action_index
                pair = pending.setdefault(key, {})
                pair[kind] = raw
                if len(pair) == 2:
                    noop, ws = check_pair(pair["action"], pair["receipt"], labels[rid][str(action_index)])
                    if noop:
                        noops.append(key)
                    if ws:
                        whitespace_only.append(key)
                    del pending[key]
    assert not pending and not any(queries.values())
    result = dict(counts=counts, shards=len(files), source_manifest_sha256=seal["source_manifest"],
                  identical_replacements=noops, equal_after_removing_whitespace=whitespace_only)
    (D/"native-audit.json").write_bytes((json.dumps(result, sort_keys=True, indent=2) + "\n").encode())
    print(dict(counts), "identical", len(noops), "equal after removing whitespace", len(whitespace_only))


if __name__ == "__main__":
    main()

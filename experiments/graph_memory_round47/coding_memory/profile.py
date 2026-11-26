"""Audit frozen actor sessions and the common scout. Never opens the grader."""
import gzip
import json
import re
import subprocess
from collections import Counter, defaultdict

from settings import B, D, ISSUE, P, dump, h, load, sha


def size(s):
    return len(s.encode("utf8"))


def response_size(obj):
    return size(json.dumps(obj, ensure_ascii=False))


def ranges_size(intervals):
    n = 0
    high = 0
    for lo, hi in sorted(intervals):
        n += max(0, hi - max(high, lo))
        high = max(high, hi)
    return n


def scout_inputs(scout):
    actions = []
    by_file = defaultdict(list)
    for item in scout["items"]:
        data = (B / item["path"]).read_bytes()
        lo = item["byte"]
        hi = lo + item["length"]
        assert data[lo:hi] == item["body"].encode() and h(data[lo:hi]) == item["sha"]
        by_file[item["path"]].append((lo, hi))
    for a in scout["actions"]:
        opts = ["rg", "--no-heading", "--with-filename", "--line-number", "--sort", "path",
                "--color", "never", "--max-count", "3", "--glob", "*.py"]
        tail = ["--", a["pattern"], "src/click"]
        direct = subprocess.run(opts + tail, cwd=B, capture_output=True)
        stats = subprocess.run(opts + ["--stats"] + tail, cwd=B, capture_output=True)
        assert direct.returncode == stats.returncode and direct.returncode in (0, 1)
        output = direct.stdout.decode().splitlines()[:a["limit"]]
        rows = [s.split(":", 2) for s in output]
        assert [[path.replace(chr(92), "/"), int(ln), line] for path, ln, line in rows] == a["hits"]
        bytes_searched = int(re.search(rb"(\d+) bytes searched", stats.stdout)[1])
        refs = [scout["items"][idx] for idx in a["receipts"]]
        actions.append(dict(pattern=a["pattern"], hits=len(rows), rg_stdout=len(direct.stdout),
                            rg_bytes_searched_replay=bytes_searched,
                            hit_text=sum(size(line) for _, _, line in rows),
                            quote_bytes=sum(r["length"] for r in refs),
                            quote_rendered=sum(size(r["rendered"]) for r in refs),
                            python_file_read_bytes=sum((B / r["path"]).stat().st_size for r in refs)))
    total = {k:sum(row[k] for row in actions) for k in actions[0] if k != "pattern"}
    return dict(actions=actions, totals=total, unique_quote_bytes=sum(r["length"] for r in scout["items"]),
                unique_quote_union=sum(ranges_size(v) for v in by_file.values()),
                unique_quotes_rendered=sum(size(r["rendered"]) for r in scout["items"]),
                issue_disk=ISSUE.stat().st_size, issue_for_ranking=size(ISSUE.read_text(encoding="utf8")),
                memory_evidence_before_ranking=total["rg_stdout"]+total["quote_rendered"],
                source_scan_and_quote_file_reads_replay=total["rg_bytes_searched_replay"]+total["python_file_read_bytes"])


def profile_actor(entry, condition, endpoint, tokens):
    label = entry["actor"]
    folder = P / label
    state = load(folder / "session.json")
    assert sha(folder / "session.json") == entry["log_sha"]
    assert state["frozen"] == entry["receipt"]
    assert sha(folder / "change.patch") == entry["receipt"]["patch_sha256"]
    assert entry["receipt"]["files"] == ["src/click/core.py"]
    assert sha(folder / "memory.txt") == load(D / "packet-seal.json")["packets"][condition]["sha"]
    prompt = (D / "ACTOR_PROMPT.txt").read_text(encoding="utf8").rstrip("\r\n")
    prompt = prompt.replace("{ACTOR}", label).replace("{ENDPOINT}", endpoint)
    opening = state["logs"][0]["response"]
    assert opening["issue"] == ISSUE.read_text(encoding="utf8")
    assert opening["memory"].encode() == (folder / "memory.txt").read_bytes()
    audit = []
    operations = Counter()
    byte = Counter()
    for event in state["logs"]:
        payload = event["request"].copy()
        resp = event["response"]
        op = payload["op"]
        operations[op] += 1
        assert event["code"] == 200
        if op in {"search", "read"}:
            assert size(resp["text"]) == resp["charged_bytes"]
            byte[op] += resp["charged_bytes"]
        if op == "edit":
            for name in ("old", "new"):
                fragment = payload.pop(name)
                payload[name+"_bytes"] = size(fragment)
                payload[name+"_sha256"] = h(fragment.encode())
                byte["edit_"+name] += size(fragment)
        row = dict(sequence=event["seq"], request=payload, code=event["code"], response=resp)
        audit.append(row)
    assert operations["start"] == operations["finish"] == 1
    assert sum(byte[k] for k in ("search","read")) == state["bytes"]
    assert state["counts"] == {k:operations[k] for k in ("search","read","edit")}
    for token in tokens:
        assert token not in json.dumps(audit)
    data = dict(actor=label, condition=condition, operations=dict(operations), bytes=dict(byte),
                source=state["bytes"], prompt=size(prompt), prompt_sha256=h(prompt.encode()),
                issue=size(opening["issue"]), memory=size(opening["memory"]),
                patch_sha256=entry["receipt"]["patch_sha256"], patch_bytes=entry["receipt"]["patch_bytes"],
                frozen_utc=entry["receipt"]["frozen_utc"], session_sha256=entry["log_sha"])
    data["source_with_memory"] = data["source"] + data["memory"]
    data["issue_memory_source"] = data["source_with_memory"] + data["issue"]
    data["prompt_issue_memory_source"] = data["issue_memory_source"] + data["prompt"]
    data["json_responses"] = sum(response_size(row["response"]) for row in audit)
    data["prompt_plus_json"] = data["prompt"] + data["json_responses"]
    return data, audit


def distinct_source(audit, pick, items):
    """Map served source to LF-normalized offsets. Search citation prefixes are metadata."""
    path = "src/click/core.py"
    raw = (B / path).read_bytes()
    source = raw.replace(b"\r\n", b"\n")
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    assert offsets[-1] == len(source)
    memory, reads, hits = [], [], []
    for i in pick:
        item = items[i]
        assert item["path"] == path
        lo = len(raw[:item["byte"]].replace(b"\r\n", b"\n"))
        fragment = item["body"].encode().replace(b"\r\n", b"\n")
        assert source[lo:lo+len(fragment)] == fragment
        memory.append((lo, lo + len(fragment)))
    edited = False
    for event in audit:
        req, resp = event["request"], event["response"]
        op = req["op"]
        if op == "edit":
            edited = True
        if op not in {"read","search"}:
            continue
        assert not edited and req["path"] == path
        if op == "read":
            fragment = resp["text"].encode()
            lo = offsets[req["start"]-1]
            assert source[lo:lo+len(fragment)] == fragment
            reads.append((lo, lo+len(fragment)))
        else:
            assert not resp["truncated"]
            for row in resp["text"].splitlines():
                rel, number, text = row.split(":", 2)
                assert rel == path
                lo = offsets[int(number)-1]
                fragment = text.encode()
                assert source[lo:lo+len(fragment)] == fragment
                hits.append((lo, lo+len(fragment)))
    return dict(memory=ranges_size(memory), reads=ranges_size(reads), hits=ranges_size(hits),
                interactive=ranges_size(hits+reads), all=ranges_size(memory+hits+reads),
                repeated_source_bytes=sum(hi-lo for lo,hi in memory+hits+reads)-ranges_size(memory+hits+reads))


def main():
    assignment = load(P / "assignment.json")
    handoff = P / "blind-grading-handoff.json"
    assert sha(P / "assignment.json") == load(D / "handoff-seal.json")["assignment"]
    assert sha(handoff) == "e65b1db110411d36f60e528fe16c0948ae3811f0a9792d5dbd68371fe0009f82"
    conditions = {a["label"]:a["condition"] for a in assignment.values()}
    endpoints = {a["label"]:a["endpoint"] for a in load(P / "launch.json")}
    reports = []
    audits = {}
    scout_data = load(D / "scout.json")
    (D / "patches").mkdir(exist_ok=True)
    for entry in load(handoff):
        label = entry["actor"]
        report, events = profile_actor(entry, conditions[label], endpoints[label], assignment)
        report["unique_lf_source"] = distinct_source(events, scout_data["chosen"][conditions[label]], scout_data["items"])
        (D / "patches" / (label + ".patch")).write_bytes((P / label / "change.patch").read_bytes())
        reports.append(report)
        audits[label] = events
    scout = scout_inputs(scout_data)
    dump(D / "profiles.json", dict(blind_lock_sha256=sha(handoff), actors=reports, scout=scout))
    content = json.dumps(audits, ensure_ascii=False, separators=(",",":"), sort_keys=True).encode()
    (D / "responses.json.gz").write_bytes(gzip.compress(content, mtime=0))


if __name__ == "__main__":
    main()

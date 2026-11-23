"""Construct equal-budget code memories exclusively from observed editor lines."""
import gzip
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from pyarrow import parquet

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
ISSUES = WORK / "graph_memory_round3/real_swe/official_verified.parquet"
OLD = WORK / "graph_memory_round11/readback/views.gz"
NEW = WORK / "graph_memory_round16/anchor_transfer/input-priors.json.gz"
WORDS = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
HEADER = re.compile(r"^(?:async\s+)?(?:class|def)\s+([A-Za-z_][A-Za-z_0-9]*)\b")
IGNORE = set("this that with from self true false none for and the return use when does would test tests python issue code file expected actual import class def should fail fails using have this then else args kwargs object".split())
BUDGET = 60


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    (ROOT / name).write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)


def load(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def tokens(text):
    words = set()
    for word in WORDS.findall(text):
        parts = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", word).split("_")
        words.update(term.lower() for term in [word, *parts] if len(term) >= 3)
    return words - IGNORE


def group_lines(selected):
    groups = []
    for path, line in sorted(selected):
        if groups and groups[-1][0] == path and groups[-1][2] == line - 1:
            groups[-1][2] = line
        else:
            groups.append([path, line, line])
    return groups


def pack(views, query):
    texts, owners = {}, {}
    first_order, last_seen = {}, {}
    for turn, event in enumerate(views):
        path = event["path"]
        first_order.setdefault(path, turn)
        last_seen[path] = turn
        stack = []
        previous = None
        for line, text in sorted(event["lines"], key=lambda row: row[0]):
            if not isinstance(line, int) or line < 1:
                raise ValueError("Invalid visible line")
            if previous != line - 1:
                stack.clear()
            stripped = text.lstrip()
            indentation = len(text.expandtabs()) - len(text.expandtabs().lstrip())
            if stripped and not stripped.startswith("#"):
                while stack and indentation <= stack[-1][0]:
                    stack.pop()
                header = HEADER.match(stripped)
                if header:
                    stack.append((indentation, header.group(1)))
            key = (path, line)
            texts[key] = text
            owners[key] = {ident for _, ident in stack}
            previous = line
    files = list(first_order)
    rows = {p: sorted(k for k in texts if k[0] == p) for p in files}
    ordered = [key for p in files for key in rows[p]]
    last_files = sorted(files, key=lambda p: -last_seen[p])
    latest = [key for p in last_files for key in rows[p]]
    first = rows[files[0]] if files else []
    last = rows[last_files[0]] if last_files else []
    half = list(dict.fromkeys(first[:30] + last[:30] + ordered))[:BUDGET]
    choices = {"first": ordered[:BUDGET], "recent": latest[:BUDGET], "split": half}
    query_words = tokens(query)
    links = 0
    for reserve in (0, 24):
        protected = first[:reserve]
        protected_set = set(protected)
        blocks = []
        for p in files:
            block = []
            for key in rows[p]:
                if key in protected_set:
                    continue
                if block and (len(block) == 12 or key[1] != block[-1][1] + 1):
                    blocks.append(block)
                    block = []
                block.append(key)
            if block:
                blocks.append(block)
        seen = [tokens("\n".join(texts[key] for key in block)) for block in blocks]
        source_names = [tokens(" ".join(sorted({name for key in block for name in owners[key]}))) for block in blocks]
        frequencies = Counter(word for words in seen for word in words)
        weights = {word: math.log((len(blocks)+1)/(frequencies[word]+1)) + 1 for word in query_words}
        def score(words):
            return sum(weights[word] for word in sorted(words & query_words))
        for use_scope in (False, True):
            scores = [score(words) + (score(names) if use_scope else 0.0)
                      for words, names in zip(seen, source_names)]
            ranked = sorted(range(len(blocks)), key=lambda i: (-scores[i], i))
            picked = list(protected)
            for index in ranked:
                picked.extend(blocks[index][:BUDGET-len(picked)])
                if len(picked) == BUDGET:
                    break
            choices[("scope" if use_scope else "lexical") + str(reserve)] = picked
        if reserve == 24:
            links = sum(bool(names & query_words) for names in source_names)
    for picked in choices.values():
        assert set(picked) <= set(texts) and len(set(picked)) == len(picked) == min(BUDGET, len(texts))
    return {"lines_seen": len(texts), "scope_matching_blocks": links,
            "pred": {arm: group_lines(keys) for arm, keys in choices.items()}}


def main():
    issue_rows = parquet.read_table(ISSUES, columns=["instance_id","base_commit","problem_statement"]).to_pylist()
    issues = {row["instance_id"]: row for row in issue_rows}
    old = load(OLD)
    new = load(NEW)
    assert not set(old).intersection(r["instance_id"] for r in new)
    records = [(iid, row["panel"], "development",row["views"][:3]) for iid,row in old.items()]
    for row in new:
        assert row["base_commit"] == issues[row["instance_id"]]["base_commit"]
        records.append((row["instance_id"], row["source"], "independent", row["views3"]))
    out = []
    for iid, source, panel, views in records:
        out.append(dict(instance_id=iid, source=source, panel=panel,
                        **pack(views, issues[iid]["problem_statement"])))
    assert len({(r["instance_id"], r["source"],r["panel"]) for r in out}) == len(out)
    write("predictions.json.gz", out)
    write("prediction-lock.json", dict(files={p.name:digest(p) for p in [
        ROOT/"PROTOCOL_RU.md", ROOT/"predict.py", ROOT/"predictions.json.gz"]},
        inputs={p.relative_to(WORK).as_posix():digest(p) for p in [NEW, OLD, ISSUES]},
        rows=dict(Counter(row["panel"] for row in out))))
    print(load(ROOT/"prediction-lock.json")["rows"])


if __name__ == "__main__":
    main()


"""Deterministic, prefix-only retrieval of previous commands. No trace execution."""
from collections import Counter
from dataclasses import dataclass
from itertools import islice
import hashlib
import json
import math
import posixpath
import re

TOKEN = re.compile(r"[a-z0-9_./-]+")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
SIGNAL = re.compile(r"error|fail|exception|cannot|not found|no such|denied|invalid|unable|missing|unknown|unrecognized|unexpected|not installed|not a |mismatch|assert", re.I)
CD = re.compile(r"^cd\s+([^\s;&]+)\s*(?:&&|;|\n)\s*")
PREFIX = re.compile(r"^(?:(?:env|sudo|time|command)\s+|[A-Za-z_]\w*=[^\s;]+\s+)")
EXT = r"pyi?|js|jsx|mjs|cjs|ts|tsx|mts|cts|go|rs|java|kt|kts|swift|php|rb|c|cc|cpp|h|hpp|sh|bash|json|toml|ini|cfg|yaml|yml|xml|md|rst|txt|sql|mod|sum|lock|gradle|vue|svelte|css|html|cs|scala|proto"
FILE = re.compile(r"(?<![\w./*?{}$~-])(?:/testbed/|(?:\./)?)(?:[\w@+-]+/)*[\w@+-][\w@.+-]*\.(?:" + EXT + r")(?![\w./*?~-])", re.I)
SUBMIT = re.compile(r"\bCOMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\b")
ARMS = ("compact", "raw_pair", "raw_pair_priority", "fingerprint", "recent_pair",
        "raw_steps", "raw_success", "recent_success", "repeat")


def clip(s, size):
    return s.encode("utf8")[:size].decode("utf8", "ignore")


def canonical(cmd):
    return cmd.replace("\r\n", "\n").strip()


def tokens(s):
    return Counter(x for x in TOKEN.findall(s.lower()) if len(x) > 1 and any(c.isalnum() for c in x))


def signature(cmd):
    script = canonical(cmd)
    base = "."
    while m := CD.match(script):
        base = posixpath.normpath(posixpath.join(base, m[1].strip("\"'")))
        script = script[m.end():]
    head = script.split("\n", 1)[0]
    while m := PREFIX.match(head):
        head = head[m.end():]
    first = re.match(r"([^\s;&|()<>]+)", head)
    family = posixpath.basename(first[1].strip("'\"")) if first else ""
    if re.fullmatch(r"python(?:[23](?:\.\d+)*)?", family):
        family = "python"
    target = ""
    for m in FILE.finditer(head):
        name = posixpath.normpath(posixpath.join(base, m[0]))
        if name.startswith("/testbed/"):
            name = name[len("/testbed/"):]
        if name.startswith(("/", "../", "tmp/", "node_modules/")):
            continue
        target = name
        break
    return family, target


def diagnostic(cmd, output, rc):
    lines = (line.strip() for line in ANSI.sub("", output).splitlines() if line.strip())
    first = ""
    chosen = ""
    for line in lines:
        if not first:
            first = line
        if SIGNAL.search(line):
            chosen = line
            break
    clean = re.sub(r"\b\d+\b", "#", (chosen or first).casefold())
    fp = clip(" ".join(clean.split()), 384)
    family = signature(cmd)[0]
    compact = "\n".join((family, str(rc), clip(cmd, 384), fp))
    return (family, rc), fp, compact


def command_of(call):
    args = (call.get("function") or {}).get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return ""
    return args.get("command", "") if isinstance(args, dict) else ""


@dataclass
class Step:
    slot: int
    cmd: str
    output: str
    rc: int | None


def parse_batch(assistant, following, counts):
    raw = (assistant.get("extra") or {}).get("actions") or []
    actions = [(a.get("command", ""), a.get("tool_call_id")) for a in raw if isinstance(a, dict)]
    if not actions:
        actions = [(command_of(a), a.get("id")) for a in (assistant.get("tool_calls") or []) if isinstance(a, dict)]
    tool = {}
    duplicates = set()
    for m in following:
        if m.get("role") != "tool":
            continue
        counts["tool_messages"] += 1
        tid = m.get("tool_call_id")
        if tid in tool:
            duplicates.add(tid)
        tool[tid] = m
    counts["ambiguous_result_ids"] += len(duplicates)
    steps = []
    for i, (cmd, tid) in enumerate(actions):
        result = tool.get(tid, {}) if tid and tid not in duplicates else {}
        extra = result.get("extra") or {}
        rc = extra.get("returncode")
        if type(rc) is not int or not isinstance(cmd, str) or not cmd.strip():
            rc = None
        cmd = cmd if isinstance(cmd, str) else ""
        content = result.get("content") or ""
        body = re.search(r"<output>(.*)</output>", content, re.S) if isinstance(content, str) else None
        out = body[1] if body else extra.get("raw_output")
        out = out if isinstance(out, str) else ""
        counts["status_unknown" if rc is None else ("status_zero" if rc == 0 else "status_nonzero")] += 1
        steps.append(Step(i, cmd, out, rc))
    counts["assistant_decisions"] += 1
    counts["declared_commands"] += len(actions)
    return steps


def each_batch(messages, counts):
    # A response beyond the next assistant decision cannot complete a previous call.
    assistant = None
    following = []
    for msg in messages:
        if msg.get("role") == "assistant":
            if assistant is not None:
                yield parse_batch(assistant, following, counts)
            assistant, following = msg, []
        elif assistant is not None:
            following.append(msg)
    if assistant is not None:
        yield parse_batch(assistant, following, counts)


@dataclass
class Record:
    origin: tuple
    source: tuple
    key: tuple
    fp: str
    cmd: str
    ordinal: int


class Index:
    def __init__(self):
        self.rows = []
        self.df = Counter()
        self.nwords = 0

    def add(self, rec, bag):
        length = bag.total()
        self.rows.append((rec, bag, length))
        self.nwords += length
        self.df.update(bag.keys())

    def ranked(self, query, key=(), fp="", priority=False):
        if not self.rows:
            return []
        n = len(self.rows)
        avg = self.nwords / n or 1
        idf = {t: math.log1p((n - self.df[t] + .5) / (self.df[t] + .5))
               for t in query if t in self.df}
        def score(row):
            rec, bag, length = row
            norm = 1.2 * (.25 + .75 * length / avg)
            result = sum(idf[t] * tf * 2.2 / (tf + norm) for t in idf if (tf := bag.get(t)))
            exact = bool(fp and rec.key == key and rec.fp == fp)
            return (exact if priority else False, rec.key == key if priority else False,
                    result, rec.ordinal)
        return [row[0] for row in sorted(self.rows, key=score, reverse=True)]


def distinct(rows):
    found = set()
    for row in rows:
        if row.cmd and row.cmd not in found:
            yield row
            found.add(row.cmd)


class Memory:
    def __init__(self):
        self.all_steps = Index()
        self.success = Index()
        self.full_pair = Index()
        self.compact_pair = Index()
        self.eligible = Counter()
        self.bytes = Counter()

    def append_step(self, b, s):
        if s.rc is None or SUBMIT.search(s.cmd):
            return
        raw = s.cmd + "\n" + s.output
        bag = tokens(raw)
        value = clip(canonical(s.cmd), 1024)
        rec = Record((b, s.slot), (b, s.slot), (), "", value, len(self.all_steps.rows))
        self.all_steps.add(rec, bag)
        size = len(raw.encode()) + len(value.encode())
        self.bytes["raw_steps"] += size
        if s.rc == 0:
            self.success.add(rec, bag)
            self.bytes["raw_success"] += size
            self.bytes["recent_success"] += len(value.encode())

    def append_pair(self, previous, b, s):
        i, f = previous
        key, fp, compact = diagnostic(f.cmd, f.output, f.rc)
        raw = f.cmd + "\n" + f.output
        value = clip(canonical(s.cmd), 1024)
        rec = Record((i, f.slot), (b, s.slot), key, fp, value, len(self.full_pair.rows))
        self.full_pair.add(rec, tokens(raw))
        self.compact_pair.add(rec, tokens(compact))
        self.eligible[key] += 1
        self.bytes["compact"] += len(compact.encode()) + len(value.encode())
        self.bytes["raw_pair"] += len(raw.encode()) + len(value.encode())
        self.bytes["raw_pair_priority"] += len(raw.encode()) + len(value.encode()) + sum(len(t.encode()) for t in (key[0], str(key[1]), fp))
        self.bytes["fingerprint"] += sum(len(t.encode()) for t in (key[0], str(key[1]), fp, value))
        self.bytes["recent_pair"] += len(value.encode())

    def predict(self, b, failure):
        key, fp, compact = diagnostic(failure.cmd, failure.output, failure.rc)
        full = tokens(failure.cmd + "\n" + failure.output)
        pair = [r for r, _, _ in reversed(self.full_pair.rows)]
        success = [r for r, _, _ in reversed(self.success.rows)]
        exact = [r for r in pair if fp and r.fp == fp and r.key == key]
        repeat = Record((b, failure.slot), (b, failure.slot), key, fp, clip(canonical(failure.cmd), 1024), 0)
        ordered = {
            "compact": self.compact_pair.ranked(tokens(compact), key, fp, True),
            "raw_pair": self.full_pair.ranked(full),
            "raw_pair_priority": self.full_pair.ranked(full, key, fp, True),
            "fingerprint": exact + pair,
            "recent_pair": pair, "raw_steps": self.all_steps.ranked(full),
            "raw_success": self.success.ranked(full), "recent_success": success, "repeat": [repeat],
        }
        results = {k: list(islice(distinct(v), 3)) for k, v in ordered.items()}
        assert all(r.source[0] < b and r.origin[0] <= r.source[0]
                   for name, rows in results.items() if name != "repeat" for r in rows)
        meta = {"fail": [b, failure.slot], "rc": failure.rc, "family": key[0],
                "fp_sha256": hashlib.sha256(fp.encode()).hexdigest() if fp else None,
                "n_pair": len(pair), "n_success": len(success), "n_steps": len(self.all_steps.rows),
                "recurrent": bool(self.eligible[key]), "fp_recurrent": bool(exact),
                "choices": {a: [[*r.origin,*r.source] for r in rows] for a, rows in results.items()}}
        return meta, results, [r.cmd for r in success]

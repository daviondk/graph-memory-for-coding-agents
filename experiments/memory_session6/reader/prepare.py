"""Materialize paired frozen reader outputs; reference scores are validated for every row."""
import collections
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sources"
SER = Path(os.getenv("SERBENCH_DIR", str(ROOT.parents[1] / "memory_session5/serbench")))
ANAPHORS = {"it", "its", "they", "them", "their", "theirs", "this", "that", "these", "those",
            "he", "she", "his", "her", "former", "latter", "same", "such"}
NAMES = ["log_words", "log_previous_events", "zero_previous_events", "unique_fraction",
         "anaphor", "leading_continuation", "digit", "initial_uppercase_fraction"]


def features(current, previous):
    words = re.findall(r"[A-Za-z0-9_]+", current)
    lower = [w.lower() for w in words]
    prefix = " ".join(lower[:2])
    return [math.log1p(len(words)), math.log1p(previous), float(previous == 0),
            len(set(lower)) / max(1, len(words)), float(bool(ANAPHORS.intersection(lower))),
            float(bool(lower and lower[0] in {"and", "but", "also", "then"}) or prefix in {"what about", "how about"}),
            float(bool(re.search(r"[0-9]", current))), sum(w[0].isupper() for w in words) / max(1, len(words))]


def zrows(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def reference(run_name):
    trec_path = SOURCE / "trec_eval-d95ca64e14a47d763ae349fb65e6d8cde4141dbd" / "trec_eval"
    paths = [trec_path, SOURCE / "qrels.txt", SOURCE / run_name]
    if os.name == "nt":
        def wslpath(p):
            return f"/mnt/{p.drive[0].lower()}/{p.as_posix()[3:]}"
        exe, qrels, run = map(wslpath, paths)
        cmd = ["wsl", "-d", os.getenv("TREC_WSL", "CodexX20MSR"), "--", exe]
    else:
        exe, qrels, run = map(str, paths)
        cmd = [exe]
    out = subprocess.check_output(cmd + ["-q", "-c", "-l", "2", "-m", "ndcg_cut.3,5", qrels, run], text=True)
    values = {}
    for line in out.splitlines():
        metric, qid, score = line.split()
        values[(qid, int(metric.rsplit("_", 1)[-1]))] = float(score)
    return values


def load_cast():
    qrels = collections.defaultdict(dict)
    for line in (SOURCE / "qrels.txt").read_text().splitlines():
        q, _, d, g = line.split()
        assert d not in qrels[q]
        qrels[q][d] = int(g)

    turns = {}
    for topic in json.loads((SOURCE / "topics.json").read_bytes()):
        for i, turn in enumerate(topic["turn"]):
            sid = f"{topic['number']}_{turn['number']}"
            turns[sid] = (str(topic["number"]), turn["raw_utterance"], i)

    arms = {}
    for arm, name in [("on", "auto.run"), ("off", "raw.run")]:
        ranked = collections.defaultdict(list)
        for line in (SOURCE / name).read_text().splitlines():
            q, _, d, _, score, _ = line.split()
            ranked[q].append((float(score), d))
        ref = reference(name)
        arms[arm] = {}
        for q, grades in qrels.items():
            docs = [d for _, d in sorted(ranked[q], reverse=True)[:5]]
            assert len(set(d for _, d in ranked[q])) == len(ranked[q])
            ideal = sorted(grades.values(), reverse=True)
            values = []
            for k in [3, 5]:
                def dcg(levels):
                    return sum(max(0, g) / math.log2(i + 2) for i, g in enumerate(levels[:k]))
                denom = dcg(ideal)
                value = dcg([grades.get(d, 0) for d in docs]) / denom if denom else 0.0
                assert abs(value - ref[q, k]) <= 0.000051, (name, q, k, value, ref[q, k])
                values.append(value)
            arms[arm][q] = {"grades": values, "rank": docs}
        for ix,k in enumerate([3, 5]):
            avg = sum(v["grades"][ix] for v in arms[arm].values())/len(qrels)
            assert abs(avg-ref["all",k]) <= 0.000051
    rows = []
    for q in sorted(qrels, key=lambda q: tuple(int(t) for t in q.split("_"))):
        topic, utterance, past = turns[q]
        rows.append({"dataset": "cast", "id": q, "group": topic, "features": features(utterance, past),
                     "on": arms["on"][q], "off": arms["off"][q]})
    return rows


def load_ser():
    sys.path.insert(0, str(SER / "upstream/src"))
    from serbench.scoring import score_predictions
    preds = [r for r in zrows(SER/"fixed_predictions.jsonl.gz") if r["method"] in {"empty", "arguments"}]
    labels = list(zrows(SER/"upstream/data/cal500/labels.jsonl.gz"))
    scored, _ = score_predictions(preds, labels, [5, 8], dataset=zrows(SER/"cal_candidates.jsonl.gz"))
    outcomes = {(r["state_id"], r["method"]): [r["mss_complete@5"], r["mss_complete@8"]] for r in scored}
    ranks = {(r["state_id"], r["method"]): r["ranked_evidence_ids"] for r in preds}
    folds = {r["state_id"]: r for r in zrows(SER/"cal_folds.jsonl.gz")}
    costs = {r["state_id"]: r["qwen_token_counts"]["arguments"] for r in zrows(SER/"trace_cost.jsonl.gz")}
    rows = []
    for r in zrows(SER/"upstream/data/cal500/items.jsonl.gz"):
        sid = r["state_id"]
        assert folds[sid]["repo"] == r["repo"]
        row = {"dataset": "ser", "id": sid, "group": r["repo"], "fold": folds[sid]["outer_fold"],
               "features": features(r.get("information_need") or "", len(r["trajectory_prefix"])),
               "on_tokens": costs[sid]}
        for arm, method in [("on", "arguments"), ("off", "empty")]:
            row[arm] = {"grades": outcomes[(sid, method)], "rank": ranks[(sid, method)]}
        rows.append(row)
    assert len(rows) == 500
    return rows


if __name__ == "__main__":
    records = load_cast() + load_ser()
    out = ROOT / "potential_outcomes.jsonl"
    data = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in records).encode()
    if out.exists():
        assert data == out.read_bytes()
    else:
        out.write_bytes(data)
    print("Official per-state scores validated", len(records), hashlib.sha256(data).hexdigest())

"""Recompute the StaleBench comparison using data files only, with stdlib Python."""
import collections
import gzip
import hashlib
import json
import pathlib
import random
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
COMMIT = "724fccc1ec4caec10b937d7e63159b4f8da7e6e5"
BASE = f"https://raw.githubusercontent.com/thenexuslab/stalebench-release/{COMMIT}/"
FILES = {
    "scores": "results/stalebench_reader_results.json",
    "questions": "release/queries_anchored_test.jsonl",
    "cosine": "release/sub_anchored_test_cosine.jsonl",
    "ordered": "release/sub_anchored_test_time_rerank.jsonl",
    "statements": "release/statements_anchored_test.jsonl",
    "keys": "release/key_anchored_test.jsonl",
}


def read_source(relative):
    cached = ROOT / "inputs" / (pathlib.Path(relative).name + ".gz")
    if cached.exists():
        raw = gzip.decompress(cached.read_bytes())
    else:
        with urllib.request.urlopen(BASE + relative, timeout=30) as response:
            raw = response.read()
        cached.parent.mkdir(exist_ok=True)
        cached.write_bytes(gzip.compress(raw, mtime=0))
    parsed = ([json.loads(line) for line in raw.splitlines() if line.strip()]
              if relative.endswith(".jsonl") else json.loads(raw))
    return parsed, hashlib.sha256(raw).hexdigest()


def summarize(rows):
    n = len(rows)
    used = sum(gate for _, _, gate in rows)
    baseline = sum(before for before, _, _ in rows)
    always = sum(after for _, after, _ in rows)
    selected = sum(after if gate else before for before, after, gate in rows)
    draws_expected = baseline + (always - baseline) * used / n
    out = dict(n=n, shown=used, never=baseline, always=always, selected=selected,
               uniform_expected_correct=draws_expected,
               difference_vs_uniform_pp=100 * (selected - draws_expected) / n)
    for gate, label in [(True, "shown"), (False, "hidden")]:
        subset = [(a, b) for a, b, active in rows if active == gate]
        out[label + "_transitions"] = dict(
            improved=sum(a < b for a, b in subset),
            worsened=sum(a > b for a, b in subset),
            stable=sum(a == b for a, b in subset),
        )
    return out


def subject_check(subjects, rows, draws=5000):
    # Supplemental uncertainty estimate, conditional on these two fixed reader logs.
    groups = collections.defaultdict(list)
    for subject, row in zip(subjects, rows):
        groups[subject].append(row)
    summary = []
    for items in groups.values():
        summary.append((len(items), sum(g for _, _, g in items),
                        sum(b - a for a, b, _ in items),
                        sum((b - a) * g for a, b, g in items)))
    rng = random.Random(20261118)
    differences = []
    for _ in range(draws):
        n, shown, gain_always, gain_gate = map(sum, zip(*rng.choices(summary, k=len(summary))))
        differences.append(100 * (gain_gate - shown / n * gain_always) / n)
    differences.sort()
    return {"unit": "Wikidata subject", "clusters": len(groups), "draws": draws,
            "seed": 20261118, "percentile_interval_pp":
            [differences[int(.025 * draws)], differences[int(.975 * draws)]]}


def main():
    data, hashes = {}, {}
    for key, path in FILES.items():
        data[key], hashes[path] = read_source(path)
    scores = data["scores"]
    questions = data["questions"]
    n = scores["config"]["n_test_facts"]
    assert n == len(questions) == 468
    assert scores["config"]["paraphrase_p"] == 0.5
    assert scores["config"]["top_k"] == 5
    assert [row["query_id"] for row in questions] == [f"test/anchored/q{i}" for i in range(n)]
    ranking = {}
    years = {row["id"]: row["year"] for row in data["statements"]}
    assert all(len(str(year)) == 4 for year in years.values())
    query_keys = {row["query_id"]: row["fact_key"] for row in data["keys"]}
    subjects = [query_keys[q["query_id"]].rsplit("_", 1)[0] for q in questions]
    for key in ("cosine", "ordered"):
        ranking[key] = {q["query_id"]: q["ranking"][:5] for q in data[key]}
        assert len(data[key]) == len(ranking[key]) == n
    gate = []
    for q in questions:
        first, second = (ranking[k][q["query_id"]] for k in ("cosine", "ordered"))
        assert len(first) == len(set(first)) == 5 and set(first) == set(second)
        assert first[2:] == second[2:]
        assert all(sid in years for sid in first)
        gate.append(first[0] != second[0])
    results, gain_sets, row_outputs = {}, {}, []
    for reader, measurements in scores["readers"].items():
        track = measurements["policy_track"]
        same_set_reordered = track["no_dates"]["time-rerank"]["context_same_set_reordered"]
        assert abs(same_set_reordered - sum(gate) / n) < 1e-8
        base, dated = (track[k]["cosine-rag"]["per_query_correct"] for k in ("no_dates", "with_dates"))
        assert len(base) == len(dated) == n
        assert set(base + dated) <= {0, 1}
        rows = [(int(a), int(b), g) for a, b, g in zip(base, dated, gate)]
        by_relation = collections.defaultdict(list)
        for q, row in zip(questions, rows):
            by_relation[q["relation"]].append(row)
            a, b, visible = row
            row_outputs.append(dict(query=q["query_id"], relation=q["relation"], reader=reader,
                                    dated=visible, plain=a, with_dates=b))
        stats = {rel: summarize(items) for rel, items in sorted(by_relation.items())}
        results[reader] = dict(overall=summarize(rows), relations=stats,
            secondary_subject_bootstrap=subject_check(subjects, rows),
            relation_macro_vs_within_relation_uniform_pp=sum(
                row["difference_vs_uniform_pp"] for row in stats.values()) / len(stats))
        gain_sets[reader] = {i for i, (a, b, _) in enumerate(rows) if a < b}
    assert len(gain_sets) == 2
    g1, g2 = gain_sets.values()
    summary = dict(repo="thenexuslab/stalebench-release", commit=COMMIT, hashes=hashes, n=n,
                   trigger=sum(gate), results=results, gains_both=len(g1 & g2),
                   extra_ascii_bytes_gate=sum(gate) * 5 * len("[2010] "),
                   extra_ascii_bytes_always=n * 5 * len("[2010] "),
                   gains_exactly_one=len(g1 ^ g2), gains_neither=n-len(g1|g2))
    (ROOT / "results.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    body = "".join(json.dumps(row) + "\n" for row in row_outputs).encode()
    (ROOT / "paired_scores.jsonl.gz").write_bytes(gzip.compress(body, mtime=0))
    print(json.dumps({r: d["overall"] for r, d in results.items()}, indent=2))


if __name__ == "__main__":
    main()

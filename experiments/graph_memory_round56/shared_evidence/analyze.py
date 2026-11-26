"""Rebuild paired differences from each hidden commit and the raw memory read logs."""
import argparse
import gzip
import json
from pathlib import Path
from statistics import fmean

HERE = Path(__file__).resolve().parent


def summarize(rows, treatment, baseline):
    delta = []
    for row in rows:
        gain = row["methods"][treatment][0] - row["methods"][baseline][0]
        delta.append(gain / (row["m"] - 1))
    return {
        "n": len(delta),
        "wins": sum(x > 0 for x in delta),
        "ties": delta.count(0),
        "losses": sum(x < 0 for x in delta),
        "delta_pp": 100 * fmean(delta),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    out = {}
    for panel in ("A", "B", "C", "long"):
        path = HERE / f"{panel}8-queries.json.gz"
        projects = json.loads(gzip.decompress(path.read_bytes()))
        projects = {repo: values for repo, values in projects.items() if values}
        rows = [r for values in projects.values() for r in values]
        pairs = [("last_shared", "last_own"), ("last_small", "last_own"),
                 ("last_small", "full"), ("hash_shared", "hash_own"),
                 ("hash_weighted", "hash_shared")]
        out[panel] = {}
        for treatment, baseline in pairs:
            pair = f"{treatment}-{baseline}"
            by_repo = {repo: summarize(values, treatment, baseline) for repo, values in projects.items()}
            pooled = summarize(rows, treatment, baseline)
            out[panel][pair] = {
                "pooled": pooled, "by_repo": by_repo,
                "macro_delta_pp": fmean(v["delta_pp"] for v in by_repo.values()),
            }
    dest = HERE / "paired.json"
    if args.verify:
        assert out == json.loads(dest.read_bytes())
    else:
        dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for panel, values in out.items():
        row = values["last_shared-last_own"]
        print(panel, row["pooled"], "macro", round(row["macro_delta_pp"], 2))
        if panel == "long":
            print(row["by_repo"])
            print("size limited", values["last_small-last_own"]["pooled"])


if __name__ == "__main__":
    main()

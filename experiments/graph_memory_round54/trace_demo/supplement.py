"""Recover eligible public Tokio path names from the pinned release. Does not load labels."""
from pathlib import Path
from hashlib import sha256
import json
import sys
import tarfile

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "next_read"
sys.path.insert(0, str(SRC))
from decide import DEFAULT_CACHE, TRACES, file_hash, original_runs, read_file


def recover(cache):
    seal = read_file(SRC / "decision-seal.json")
    for name, checksum in seal["sources"].items():
        assert file_hash(cache / name) == checksum
    ranks = read_file(SRC / "fusion-inputs.json.gz")
    explicit = read_file(SRC / "explicit-decisions.json.gz")
    runs, _, _ = original_runs(cache)
    cohort = {q: t for q, t in runs.items() if t["repo"].lower() == "tokio-rs/tokio"}
    with tarfile.open(cache / TRACES) as archive:
        for member in archive:
            if "/traces_" in member.name and member.isfile():
                row = json.load(archive.extractfile(member))
                if row["sample_id"] in cohort:
                    cohort[row["sample_id"]]["proposals"] = row["suggested_unread_files"]
    result = {}
    for q, trace in sorted(cohort.items()):
        candidates = set(trace["proposals"]).union(trace["strict"], trace["reads"], *trace["ranks"].values())
        eligible = set(ranks[q]["lexical_order"]).union(explicit[q]["opened"], explicit[q]["strict"])
        hashed = {sha256((trace["repo"] + "\0" + p).encode()).hexdigest(): p for p in sorted(candidates)}
        assert eligible <= hashed.keys()
        result[q] = dict(repo=trace["repo"], commit=trace["commit"], paths={h: hashed[h] for h in sorted(eligible)})
    assert set(result) == {q for q,x in explicit.items() if x["repo"].lower() == "tokio-rs/tokio"}
    (HERE/"tokio-paths.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    print(f"Recovered path names for all {len(result)} eligible Tokio traces from verified archives.")

if __name__ == "__main__":
    recover(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CACHE)


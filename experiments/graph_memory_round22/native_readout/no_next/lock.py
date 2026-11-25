import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[2]
F = WORK / "graph_memory_round20/factor_reader"
G = WORK / "graph_memory_round20/residual_graph"
C = G / "adjacency_control/full"
D = WORK / "graph_memory_round19/trained_rank"
GOLD = WORK / "graph_memory_round18/isetrace_official/gold-spans.json.gz"
PAPER_SEAL = "3fcc458d76428fcd5e8d2f6da7954d199dcc48cd22078dfb3615b75e6372c2d2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def annotation():
    return (
        "PLAN_RU.md was committed to local storage before this reviewer inspected individual "
        "no-next rank records. At this independent lock the producer's eight shards and seal "
        "already exist and aggregate arm results could be known. This is not prospective "
        "blind benchmark registration. Artifact hashes and tuning are fixed before the "
        "new joint statistical analysis."
    )


def main():
    files = [HERE / "PLAN_RU.md", HERE.parent / "holm_audit.py", HERE.parent / "holm-audit.json",
             GOLD, D / "split.json.gz", D / "forecast-seal.json", F / "hash64-seal.json",
             F / "metrics-test-rows.json.gz", F / "metrics-full-rows.json.gz"]
    for folder in [G, C]:
        files.extend([folder / "forecast-seal.json", folder / "checkpoint.json"])
    files.extend([C / "prediction-plan.json", C / "model-lock.json"])
    assert sha(C / "forecast-seal.json") == PAPER_SEAL
    seals = {str(path.relative_to(WORK)): sha(path) for path in files}
    output = dict(sha256=seals, annotation=annotation(),
                  no_next_ready=len(list(C.glob("forecasts-rgcn-*.json.gz"))), code_sha256=sha(Path(__file__)))
    snapshot = json.dumps(output, indent=2, sort_keys=True) + "\n"
    target = HERE / "input-plan.json"
    if target.exists():
        assert target.read_text(encoding="utf8") == snapshot
    else:
        target.write_text(snapshot, encoding="utf8")
    print(sha(target))


if __name__ == "__main__":
    main()

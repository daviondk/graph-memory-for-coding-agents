"""Reuse the frozen G1 writer; add a matched concentration control on new repositories."""
import datetime as dt
import json
import platform
import random
import statistics
import sys
from pathlib import Path

import run


class MatchedMemory(run.Memory):
    def score(self, anchor, index):
        ranked, experts = super().score(anchor, index)
        if not experts:
            ranked["mass_matched_raw"] = []
            return ranked, experts
        prior = experts[0]
        raw = self.raw.get(anchor, {})
        unit = self.unit.get(anchor, {})
        total = sum(raw.get(f, 0) for f in prior)
        scale = sum(unit.get(f, 0) for f in prior) / total if total else 0.0
        scores = {f: scale * raw.get(f, 0) + 4 * prior[f] for f in prior}
        ranked["mass_matched_raw"] = sorted(prior, key=lambda f: (-scores[f], -self.frequency[f], f))[:5]
        return ranked, experts


def contrast(summary, a, b):
    paired = [v["ranking"][a]["r5"] - v["ranking"][b]["r5"] for v in summary["per_repo"].values()]
    rng = random.Random(20261118)
    distribution = sorted(statistics.fmean(rng.choices(paired, k=len(paired))) for _ in range(20000))
    return {"delta": statistics.fmean(paired), "interval95": [distribution[499], distribution[19499]],
            "wins_ties_losses": [sum(v > 1e-12 for v in paired), sum(abs(v) <= 1e-12 for v in paired), sum(v < -1e-12 for v in paired)]}


if __name__ == "__main__":
    run.METHODS = run.METHODS + ["mass_matched_raw"]
    run.Memory = MatchedMemory
    pins = json.loads((run.HERE / "transfer_pins.json").read_text())
    out = run.HERE / "transfer_run"
    out.mkdir(exist_ok=False)
    inv = []
    log = out / "predictions.jsonl"
    with log.open("w", encoding="utf-8", newline="\n") as writer:
        for p in pins:
            if "sha" in p:
                inv.append(run.replay(p, run.HERE / "transfer_mirrors" / p["repo"], writer))
    study = run.summarize([json.loads(s) for s in log.read_text().splitlines()])
    for block in study.values():
        block["matched_primary"] = contrast(block, "unit_smoothed", "mass_matched_raw")
        block["unmatched_secondary"] = contrast(block, "unit_smoothed", "raw_smoothed")
    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(study, indent=2), encoding="utf-8")
    sigs = [run.HERE / f for f in ("TRANSFER_PROTOCOL.md", "run.py", "transfer.py", "transfer_pins.json")]
    meta = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "manifest": inv, "python": sys.version,
            "platform": platform.platform(), "git": run.git(run.HERE, "--version").decode().strip(),
            "hashes": {f.name: run.hash_file(f) for f in sigs + [log, summary_path]}}
    (out / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in study["evaluation"].items() if k != "per_repo"}, indent=2))

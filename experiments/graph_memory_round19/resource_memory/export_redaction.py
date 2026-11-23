"""Verify the exact transform from private pytest logs to the portable artifacts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
FILES = ("forecasts.json.gz", "current-runs.json.gz")
TEMP_PATH = re.compile(
    r"(?i)\b[a-z]:[\\/]+users[\\/]+[^/'\"\\\r\n]+[\\/]+appdata[\\/]+local"
    r"[\\/]+temp[\\/]+pytest-[^'\"\r\n]+"
)
REPLACEMENT = "<pytest-temp>"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render(original):
    decoded = gzip.decompress(original)
    expected = json.loads(decoded)
    matches = []
    rows_changed = 0
    for record in expected:
        text = record["log"]
        found = TEMP_PATH.findall(text)
        if found:
            matches.extend(found)
            rows_changed += 1
            record["log"] = TEMP_PATH.sub(REPLACEMENT, text)
    assert rows_changed == 1 and len(matches) == len(set(matches)) == 2
    for old in matches:
        raw = json.dumps(old, ensure_ascii=False)[1:-1].encode("utf-8")
        assert decoded.count(raw) == 1
        decoded = decoded.replace(raw, REPLACEMENT.encode("ascii"), 1)
    assert json.loads(decoded) == expected
    return gzip.compress(decoded, mtime=0), digest(decoded)


def verify(private=None):
    receipt = json.loads((ROOT / "export-receipt.json").read_bytes())
    for name in FILES:
        row = receipt["logs"][name]
        public = (ROOT / name).read_bytes()
        raw = gzip.decompress(public)
        assert digest(public) == row["export_sha256"] and digest(raw) == row["normalized_plain_sha256"]
        records = json.loads(raw)
        assert len(records) == row["rows"]
        assert [r["log"].count(REPLACEMENT) for r in records].count(2) == 1
        assert sum(r["log"].count(REPLACEMENT) for r in records) == 2
        assert all(not TEMP_PATH.search(r["log"]) for r in records)
        if private:
            original = (private / name).read_bytes()
            assert digest(original) == row["original_sha256"]
            rendered, token = render(original)
            assert gzip.decompress(rendered) == raw and token == row["normalized_plain_sha256"]
    assert digest((ROOT / "forecast-seal.json").read_bytes()) == receipt["export_forecast_seal_sha256"]
    if private:
        for src, key in [("MANIFEST_SHA256.json", "original_manifest_sha256"), ("forecast-seal.json", "original_forecast_seal_sha256")]:
            assert digest((private / src).read_bytes()) == receipt[key]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-originals", type=Path)
    verify(parser.parse_args().private_originals)
    print("OK both portable logs and export receipt")

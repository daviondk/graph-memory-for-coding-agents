"""Fetch the pinned source and official grader and build local package metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "evaluator"
TAG = "pybamm-team__pybamm-4267"
COMMIT = "7152cf96809b45343ccc1caf7115a7d3fa43f956"
VENDOR = {"eval.py": "e580d953b75e5182a66ffd2fecfbf9c756dadd89db767cfd42bd251f956a7108", "log_parsers.py": "818560dab8da86cecc31cd9484a0f2b770359e59c51613316a391b58a73885e1", "swe_constants.py": "823dd1ef512d363ed5d4dce05d70f22d7f93b25722cda5b0971f17010f5168a5"}

def fetch(url, dest, sha):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        data = dest.read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=90) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError(f"SHA-256 mismatch in {dest}")
    if not dest.is_file():
        dest.write_bytes(data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, default=STATE / "venv/Scripts/python.exe")
    args = parser.parse_args()
    py = args.python.resolve()
    target = next(row for row in json.loads((ROOT/"screen.json").read_bytes())["selected"] if row["instance"] == TAG)
    archive = STATE / "archive" / (TAG + ".tar.gz")
    fetch(target["archive"]["url"], archive, target["archive"]["sha256"])
    vendor_parent = Path(os.environ.get("VIBE_CHECKOUT", "D:/CodexResearch/x20-official-vibe/VibeMemBench")).resolve()
    for name, sha in VENDOR.items():
        url = f"https://raw.githubusercontent.com/AlibabaResearch/DAMO-ConvAI/{COMMIT}/VibeMemBench/scripts/vendor/{name}"
        fetch(url, vendor_parent/"scripts/vendor"/name, sha)
    import grade_patch
    site = Path(subprocess.check_output([str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"], text=True).strip())
    if not list(site.glob("pybamm-*.dist-info")):
        with tempfile.TemporaryDirectory(dir=STATE) as directory:
            repo = Path(directory).resolve()
            grade_patch.extract_source(archive, repo)
            subprocess.run([str(py), "-B", "setup.py", "dist_info", "--output-dir", str(site)], cwd=repo, check=True)
    print("Pinned source, scorer modules, and package metadata are available.")

"""Reproduce selected computations from the delivered ZIP in a fresh temporary directory on D."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

BASE = Path(__file__).resolve().parent
WORK = BASE.parent.resolve()
OUTPUT = BASE.parents[1] / "outputs"

def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()

def run(cwd, script):
    env = dict(os.environ, PYTHONPATH="", PYTHONIOENCODING="utf8")
    completed = subprocess.run([sys.executable, script], cwd=cwd, env=env, check=True,
                               encoding="utf8", capture_output=True, timeout=160)
    return completed.stdout.strip()

def main():
    zfile = OUTPUT / "graph-memory-round3-records.zip"
    with tempfile.TemporaryDirectory(dir=WORK, prefix="r3-verification-") as scratch:
        root = Path(scratch).resolve()
        assert root.parent == WORK and root.name.startswith("r3-verification-")
        with ZipFile(zfile) as archive:
            for name in archive.namelist():
                assert (root / name).resolve().is_relative_to(root)
            archive.extractall(root)
        experiment = root / "work" / BASE.name
        manifest = run(experiment, "check_package.py")
        before = json.loads((experiment / "geometry_results.json").read_bytes())
        geometry = run(experiment, "geometry.py")
        assert json.loads((experiment / "geometry_results.json").read_bytes()) == before
        with gzip.open(experiment / "geometry_by_action.jsonl.gz", "rt", encoding="utf8") as generated:
            with gzip.open(BASE / "geometry_by_action.jsonl.gz", "rt", encoding="utf8") as original:
                assert generated.read() == original.read()
        original_summary = sha(experiment / "class_memory" / "RESULTS_RU.md")
        run(experiment/"class_memory", "summarize.py")
        assert sha(experiment/"class_memory"/"RESULTS_RU.md") == original_summary
        source_audit = json.loads((experiment/"report/final/numeric_audit.json").read_bytes())
        run(experiment/"report", "numeric_audit.py")
        repeat_audit = json.loads((experiment/"report/final/numeric_audit.json").read_bytes())
        assert repeat_audit == source_audit
        verified_docs = json.loads((experiment/"report/final/published.json").read_bytes())
        for entry in verified_docs:
            dest = OUTPUT / entry["file"]
            assert sha(dest) == entry["sha256"] and dest.stat().st_size == entry["bytes"]
        summary = {"manifest":manifest, "geometry_recomputed":geometry.splitlines(),
                   "class_summary_identical":True, "manuscript_numbers_checked":repeat_audit["checked_values"],
                   "reports_verified":verified_docs, "zip_sha256":sha(zfile), "zip_bytes":zfile.stat().st_size}
    (OUTPUT / "graph-memory-round3-verification.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(summary,ensure_ascii=True))

if __name__ == "__main__":
    main()

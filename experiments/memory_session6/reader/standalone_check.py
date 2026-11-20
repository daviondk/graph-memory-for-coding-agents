"""Validate a clean, offline refit against saved artifacts."""
import filecmp
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parent
INPUTS = ["switch.py", "prepare.py", "potential_outcomes.jsonl", "source_receipt.json", "preregistration.md",
          "audit.py", "count_control.py", "sources/topics.json"]
OUTPUTS = ["results.json", "models.json", "decisions.jsonl", "control_audit.json", "count_control.json"]

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        other = Path(d)
        for name in INPUTS:
            (other/name).parent.mkdir(exist_ok=True,parents=True)
            shutil.copyfile(BASE/name,other/name)
        for script in ["switch.py","audit.py","count_control.py"]:
            subprocess.run([sys.executable,str(other/script)],check=True,stdout=subprocess.DEVNULL)
        for name in OUTPUTS:
            assert (BASE/name).read_text(encoding="utf8")== (other/name).read_text(encoding="utf8"), name
    print("PASS offline refit, all 708 outcome pairs, 1416 decisions, 4 primary and 4 secondary estimates, controls")


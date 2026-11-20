"""Run all independent R5 checks after the original reference receipt and G model decision exist."""
from pathlib import Path
import subprocess
import sys
import time


def wait_for(*files):
    while not all(path.is_file() for path in files):
        time.sleep(5)


def main():
    review=Path(__file__).resolve().parent
    reader=review.parent/"reader"
    wait_for(reader/"original_targets_receipt.json",reader/"G_decisions.json")
    for args in (["audit_reader.py","both"],["audit_adaptive.py"],["audit_allocation.py"],["score_ast_gate.py"],["score_g.py"]):
        print("starting",*args,flush=True)
        subprocess.run([sys.executable,"-u",*args],cwd=review,check=True)
    wait_for(*(reader/f"{s}_items.json.gz" for s in ("A","B","C","F")))
    subprocess.run([sys.executable,"-u","reconcile.py"],cwd=review,check=True)
    print("ALL R5 INDEPENDENT CHECKS PASSED",flush=True)
if __name__=="__main__":main()


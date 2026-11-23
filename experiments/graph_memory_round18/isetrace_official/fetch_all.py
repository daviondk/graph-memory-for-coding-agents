"""Provision all immutable released shards, with a retry for transient network failures."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import sys
import time
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parents[1]/"graph_memory_round17"/"isetrace"
sys.path.insert(0,str(BASE))
import provision
specs=[(provision.RAW,"datasets",f"trajectories/trajectories-{i:05d}.jsonl") for i in range(8)]+provision.SPECS[1:]
def action(spec):
    for attempt in range(3):
        try:return provision.fetch(spec)
        except Exception:
            if attempt==2:raise
            time.sleep(1)
if __name__=="__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:items=list(e.map(action,specs))
    data=json.dumps(items,indent=2)+"\n"
    dest=ROOT/"source-lock.json"
    if dest.exists():assert dest.read_text("utf8")==data
    else:dest.write_text(data,encoding="utf8",newline="\n")

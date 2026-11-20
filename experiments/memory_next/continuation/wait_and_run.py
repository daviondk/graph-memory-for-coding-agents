"""Wait for all four parent checkpoints and exclusive use of the single solver slot."""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from handoff import ROOT,OLD,read
from continue_runs import main

if __name__=="__main__":
    ids=sorted({i for i,a in read(ROOT/"assignments.json")})
    log=ROOT/"queue.log"
    def record(msg):
        with log.open("a",encoding="utf-8") as f:f.write(datetime.now(timezone.utc).isoformat()+" "+msg+"\n")
        print(msg,flush=True)
    prev=None
    while True:
        parents=tuple(i for i in ids if (OLD/"runs"/i/"brief"/"complete.json").exists())
        guard=(ROOT.parent/"time_read"/"end_lock.json").exists()
        state=(parents,guard)
        if state!=prev:
            record(f"parents {len(parents)}/4; prerequisite locked {guard}")
            prev=state
        if parents==tuple(ids) and guard: break
        time.sleep(9)
    if not (ROOT/"end_lock.json").exists():
        for attempt in range(3):
            try:
                main()
                break
            except (requests.Timeout,requests.ConnectionError,requests.HTTPError) as exc:
                record(f"HTTP failure on attempt {attempt+1}: "+repr(exc))
                if attempt==2:raise
                time.sleep(8*(attempt+1))
        record("eight candidate patches frozen")


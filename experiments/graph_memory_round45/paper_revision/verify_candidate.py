"""Verify file integrity and exercise the actual HTTP readers and independent audits."""
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from demo import D, child, verify_assets

def fetch(url, route, **query):
    with urlopen(url + route + "?" + urlencode(query), timeout=15) as response:
        return json.load(response)

def main():
    receipt = json.loads((D/"CONTENT_SHA256.json").read_bytes())
    for name, expected in receipt.items():
        if sha256((D/name).read_bytes()).hexdigest() != expected:
            raise ValueError("Digest mismatch: " + name)
    verify_assets()
    with ExitStack() as servers:
        trace = servers.enter_context(child(D/"apps/trace/launcher.py"))
        code = servers.enter_context(child(D/"apps/code/app.py"))
        context = servers.enter_context(child(D/"apps/context/server.py"))
        flow = servers.enter_context(child(D/"apps/flow/server.py"))
        visited=0
        for case in ("withdrawn","overlap","accumulating"):
            default=fetch(flow,"/snapshot",case=case)
            for step in range(1,1+default["total"]):
                audit=fetch(flow,"/audit",case=case,step=step)
                assert audit["audit"]["matches"] and audit["step"]==step
                visited+=1
        assert visited==84
        for policy, ids in [("file",[]),("range",[]),("edges",[0]),("local",[0,1])]:
            evidence=fetch(context,"/audit",case="interior",policy=policy,budget=2048)
            assert evidence["selected"]==ids and evidence["audit"]["mismatches"]==0
        initial = fetch(trace, "/api/packet", q="q02", b=2048)
        controls = [r for r in initial["sources"] if r["selected"]]
        for source in controls:
            new = fetch(trace, "/api/packet", q="q02", b=2048, s=source["id"])
            if new["added"] == [19] and new["removed"] == [11]:
                checked = fetch(trace, "/api/audit", q="q02", b=2048, s=source["id"])["audit"]
                assert checked["full_matches"] and checked["covered_chars"] == checked["gold_chars"] == 60
                break
        else:
            raise AssertionError("The documented selected-source example is missing")
        irrelevant = next(r["id"] for r in initial["sources"] if not r["selected"] and not r["barrier"])
        assert fetch(trace,"/api/packet",q="q02",b=2048,s=irrelevant)["action"] == "Reuse cached packet"
        for case, before, after in [("relocated",315,315),("changed",507,74),("stale",2044,2044)]:
            row = fetch(code, "/api/packet", case=case)
            assert (row["baseline"]["bytes"],row["span"]["bytes"]) == (before, after)
            audit = fetch(code, "/api/audit", case=case)
            if case=="relocated":
                assert audit["verified_reuse"]
            if case=="stale":
                assert len(audit["selected_mismatch"]) == 3
                assert audit["selected_mismatch"] == audit["selected_prior_mismatch"]
    print(f"Verified {len(receipt)} files and all four live SQLite consoles.")

if __name__=="__main__":
    main()

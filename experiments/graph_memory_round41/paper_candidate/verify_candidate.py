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
    print(f"Verified {len(receipt)} files and both live SQLite demos.")

if __name__=="__main__":
    main()

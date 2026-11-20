"""Independently remove every future message and verify the sealed inputs byte-for-byte."""
import collections
import io
import json
from pathlib import Path
import prefix
import rank

ROOT = Path(__file__).resolve().parent

class ClippedOnly:
    def __init__(self, payload):
        self.payload = payload
    def __truediv__(self, name):
        return self
    def read_bytes(self):
        return self.payload

def main(panel):
    rank.D = panel
    originals = prefix.V
    roster = {r["iid"]: r for r in rank.load("roster.json")}
    groups = collections.defaultdict(list)
    for r in rank.load("inputs.json.gz"):
        groups[r["iid"]].append(r)
    verified = []
    try:
        for iid, rows in groups.items():
            info = roster[iid]
            public = (originals / "benchmark" / info["file"]).read_bytes()
            assert prefix.h(public) == info["sha"]
            messages = json.loads(public)["messages"]
            for row in rows:
                # The extractor has access to the original user description and all messages
                # up through the empty tool response. No following message exists in this view.
                cut = prefix.enc({"messages":messages[:row["message"] + 1]})
                prefix.V = ClippedOnly(cut)
                records = list(prefix.sample({**info,"sha":prefix.h(cut)}))
                last = records[-1]
                assert prefix.enc(last) == prefix.enc(row)
                verified.append({"id":row["id"],"last_message":row["message"],
                                 "prefix_sha":prefix.h(cut),"state_sha":prefix.h(prefix.enc(row))})
    finally:
        prefix.V = originals
    rank.dump("prefix_invariance.json.gz", verified)
    print(panel.name, len(verified), "unchanged inputs with all future messages removed")

if __name__ == "__main__":
    for panel in (ROOT, ROOT/"replication"):
        main(panel)

"""Repack sealed address choices under the same byte ceiling and count delivered references."""
from collections import defaultdict
import struct
from prepare import ROOT, CACHE, read, dump, sha
from score import grouped_interval

def main():
    raw = ROOT/"outcomes.json.gz"
    assert sha(raw.read_bytes()) == read(ROOT/"results.json")["outcomes"]
    packet = {r["id"]: dict(r["records"]) for r in read(CACHE/"packets.json.gz")}
    panel = [r for r in read(raw) if r["reachable"]]
    output = {}
    trace = []
    for budget in (256, 512, 1024):
        totals = {}
        compare = []
        for row in panel:
            arms = {}
            for policy, picks in row["methods"].items():
                delivered = []
                message = bytearray()
                for addr, checksum in zip(picks["opened"][:2], picks["digests"]):
                    body = packet[row["id"]][addr].encode()
                    assert sha(body) == checksum
                    head = struct.pack(">QH",int(sha((row["id"]+"|"+str(addr)).encode())[:16],16),len(body))
                    if len(message) + len(head) + len(body) <= budget:
                        message += head + body
                        delivered.append(addr)
                success = int(not set(row["target"]).isdisjoint(delivered))
                arms[policy] = {"hit2":success}
                trace.append({"budget":budget, "id":row["id"], "policy":policy, "addresses":delivered,
                              "message_sha":sha(message), "bytes":len(message), "hit":success})
                tot = totals.setdefault(policy, {"hit":0,"bytes":0,"records":0})
                tot["hit"] += success
                tot["bytes"] += len(message)
                tot["records"] += len(delivered)
            compare.append({"family":row["family"],"methods":arms})
        output[str(budget)] = {"n":len(panel), "methods":totals, "primary":grouped_interval(compare,"signature","hybrid")}
    dump(ROOT/"budget-outcomes.json.gz",trace)
    dump(ROOT/"budget-results.json",{"conditions":output, "per_query_sha":sha((ROOT/"budget-outcomes.json.gz").read_bytes()),
                                     "protocol":sha((ROOT/"BUDGET_PROTOCOL_RU.md").read_bytes())})
    print({b:{m:v["hit"] for m,v in s["methods"].items()} for b,s in output.items()})
if __name__ == "__main__":
    main()

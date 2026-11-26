"""Audit stored packet membership, deterministic ordering, grant budget and published totals."""
from collections import defaultdict
from pathlib import Path
import gzip,hashlib,json,sqlite3
D=Path(__file__).resolve().parent
def zipped(path):
    return json.loads(gzip.decompress(path.read_bytes()))
def main():
    ledger=zipped(D/"packets.json.gz")
    report=json.loads((D/"results.json").read_bytes())
    seals=json.loads((D/"inputs.json").read_bytes())
    assert hashlib.sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest()==seals["protocol"]
    assert len(ledger)==report["trajectories"]==40
    for cap in (1,4):
        all_events=[(q,e) for q,a in ledger.items() for e in a["events"] if e["cap"]==cap]
        assert len(all_events)==len({(q,e["step"],e["a"],e["b"]) for q,e in all_events})
        r=report["policies"][str(cap)];assert r["pairs"]==len(all_events)
        count_change=count_joint=total_ids=0;groups=set()
        for q,e in all_events:
            groups.add((q,e["step"]))
            old,l,rgt,new=(e[k] for k in ("before","first","second","after"))
            for ids in (old,l,rgt,new):
                assert len(set(ids))==len(ids) and old[:e["prefix"]]==ids[:e["prefix"]]
            if not e["x"]:assert l==old and rgt==new
            if not e["y"]:assert rgt==old and l==new
            if e["total_cost"]<=2048:assert l==rgt==new==old
            count_change+=int(old!=new)
            count_joint+=int(old==l==rgt and new!=old)
            total_ids+=len(set(old)^set(new))
        assert count_change==r["changed"] and count_joint==r["joint_only"] and total_ids==r["sum_id_differences"] and len(groups)==r["groups"]
    recorded=zipped(D/"group-packets.json.gz")
    rg=json.loads((D/"group-results.json").read_bytes())
    assert hashlib.sha256((D/"GROUP_CONTROL_RU.md").read_bytes()).hexdigest()==rg["protocol_sha256"]
    for cap in (1,4):
        cases=[r for q,rs in recorded.items() for r in rs if r["cap"]==cap]
        assert len(cases)==1072 and all(not r["signs_safe"] or r["base"]==r["after"] for r in cases)
        for label,block in (("all",cases),("joint",[r for r in cases if r["count"]>=2]),("single",[r for r in cases if r["count"]==1]),("unchanged_counts",[r for r in cases if not r["count"]])):
            m=rg[str(cap)][label];assert m["n"]==len(block) and m["changed"]==sum(r["base"]!=r["after"] for r in block)
            assert m["only_joint"]==sum(r["base"]!=r["after"] and len(r["single_same"])==r["count"] for r in block)
    print("Verified all stored packet contrasts, zero shifts, cardinalities and group denominators.")
if __name__=="__main__":main()

"""Repeat paired intervals with near-duplicate source versions assigned the same block."""
from prepare import ROOT, read, dump, sha
from score import grouped_interval

def main():
    data = read(ROOT/"data-audit.json")
    components = data["document_reuse"]["map_jaccard90"]
    rows = []
    for row in read(ROOT/"outcomes.json.gz"):
        if row["reachable"]:
            key = sha(("contradoc-family-v1|" + row["family"]).encode("ascii"))[:16]
            mapped = dict(row, family=components[key])
            rows.append(mapped)
    stats = {p:grouped_interval(rows,p,"hybrid") for p in ("signature","local_fusion","neighbor","e5","bm25")}
    dump(ROOT/"family-sensitivity.json", {"components":len({r["family"] for r in rows}),
           "audit":sha((ROOT/"data-audit.json").read_bytes()), "contrasts":stats})
    print(stats["signature"])
if __name__=="__main__":
    main()

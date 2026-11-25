"""Verify exact comparator outcomes including the negative NMS result."""
import argparse
from diverse import D,prep,read,save,sha
FILES=("PROTOCOL_RU.md","diverse.py","plan.json","selected.json.gz","cache-seal.json","rows.json.gz","result-seal.json","analyze.py","results.json","REPORT_RU.md","verify.py")
def main():
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");p.add_argument("--private",action="store_true");args=p.parse_args()
    r=read(D/"results.json");s=read(D/"result-seal.json");b=read(D/"cache-seal.json")
    assert r["strict"]==s["strict"]==12096 and s["rows"]==sha(D/"rows.json.gz") and b["picks"]==sha(D/"selected.json.gz")
    assert r["counts"]["all"]["nms3064"]["exact_oracle_hit"]==482 and r["counts"]["all"]["pareto64"]["exact_oracle_hit"]==457
    if args.private:
        import sqlite3
        *_,dest=prep()
        for n,entry in b["sqlite"].items():
            path=dest/(n+".sqlite");assert sha(path)==entry["sha"] and path.stat().st_size==entry["bytes"]
            with sqlite3.connect(path) as db:assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    value={f:sha(D/f) for f in FILES};path=D/"manifest.json"
    if args.seal and not path.exists():save(path,value)
    assert read(path)==value;print("verified",len(value),sha(path))
if __name__=="__main__":main()

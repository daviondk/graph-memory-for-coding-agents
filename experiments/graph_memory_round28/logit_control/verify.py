"""Verify the fixed-snapshot logit study."""
import argparse
from control import D,PAR,sha,read,save,plan,ARMS
FILES=("PROTOCOL_RU.md","control.py","plan.json","window-build.json.gz","build-seal.json","validation-costs.json.gz",
       "latency.json.gz","measurement-seal.json","analyze.py","results.json","TRANSACTION_RU.md","transaction.py",
       "transaction-samples.json.gz","transaction-results.json","REPORT_RU.md","verify.py")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--seal",action="store_true");parser.add_argument("--private",action="store_true");args=parser.parse_args()
    p,cases,_,old,new=plan()
    a=read(D/"results.json");b=read(D/"build-seal.json");m=read(D/"measurement-seal.json");tx=read(D/"transaction-results.json")
    assert len(p["qids"])==a["questions"]==96 and a["conditions"]==2202 and len(ARMS)*2202==m["strict"]==28626
    assert a["latency_measurements"]==m["timings"]==18720 and tx["n"]==6144 and tx["samples"]==sha(D/"transaction-samples.json.gz")
    assert 53==a["costs"]["zip-64-bound"]["all"]["recomputed_windows"]["total"]
    if args.private:
        import sqlite3
        for n,s in b["files"].items():
            path=new/(n+".sqlite");assert sha(path)==s["sha"] and path.stat().st_size==s["bytes"]
            with sqlite3.connect(path) as db:assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    hashes={p:sha(D/p) for p in FILES};dest=D/"manifest.json"
    if args.seal and not dest.exists():save(dest,hashes)
    assert read(dest)==hashes;print("verified",len(hashes),sha(dest))
if __name__=="__main__":main()

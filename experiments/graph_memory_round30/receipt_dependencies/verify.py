"""Check source disjointness and equality of all three receipt-aware write decisions."""
import argparse
from build import D,read,save,sha,sources
FILES=("PROTOCOL_RU.md","inputs.py","plan.json","events.json.gz","event-seal.json","build.py","build-rows.json.gz","build-seal.json","evaluate.py","answers.json.gz","latency.json.gz","result-seal.json","summary_stats.py","results.json","REPORT_RU.md","verify.py")
def main():
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");p.add_argument("--private",action="store_true");args=p.parse_args()
    r=read(D/"results.json");c=read(D/"result-seal.json");a=read(D/"answers.json.gz");ev=read(D/"events.json.gz")
    assert r["strict"]==94464 and r["timing_n"]==13824 and c["answers"]==sha(D/"answers.json.gz")
    for q,case in ev.items():
        reg=case["registry"];assert all(u[1]<=v[0] for u,v in zip(reg,reg[1:]))
        for row in a[q].values():
            for k in ("8","64"):
                x=row["arms"];assert x["producer"+k]==x["mask_group"+k]==x["mask_pareto"+k]
    if args.private:
        import sqlite3
        *_,dest=sources()
        for m,v in read(D/"build-seal.json")["files"].items():
            path=dest/(m+".sqlite");assert sha(path)==v["sha"]
            with sqlite3.connect(path) as db:
                assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
                if m!="registry":assert all(int(s).bit_count()==1 for s, in db.execute("SELECT mask FROM r"))
    hashes={f:sha(D/f) for f in FILES};path=D/"manifest.json"
    if args.seal and not path.exists():save(path,hashes)
    assert read(path)==hashes;print("verified",len(hashes),sha(path))
if __name__=="__main__":main()

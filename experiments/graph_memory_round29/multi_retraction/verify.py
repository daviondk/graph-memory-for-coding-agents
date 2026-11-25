"""Verify the four physical controls and all candidate witness counts."""
import argparse
from multiban_design import D,read,save,sha
from store import state
FILES=("PROTOCOL_RU.md","multiban_design.py","plan.json","scenario-seal.json","scenarios.json.gz","store.py","build-rows.json.gz","build-seal.json",
       "measure.py","predictions.json.gz","latency.json.gz","measurement-seal.json","analyze.py","results.json","witness.py","witnesses.json.gz","witness-seal.json","REPORT_RU.md","verify.py")
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--seal",action="store_true");parser.add_argument("--private",action="store_true");args=parser.parse_args()
    a=read(D/"results.json");m=read(D/"measurement-seal.json");w=read(D/"witness-seal.json")
    assert m["strict"]==a["strict"]==3456 and m["timings"]==a["latency_trials"]==11520
    assert w["self"]==a["construction"]["pareto"]==275917 and w["all"]==6677914 and w["dominated"]==6401997
    assert w["rows"]==sha(D/"witnesses.json.gz") and m["latency"]==sha(D/"latency.json.gz")
    assert a["main_cases"]==576 and sum(a["case_counts"].values())==570
    if args.private:
        import sqlite3
        _,_,_,_,base=state()
        for n,v in read(D/"build-seal.json")["files"].items():
            f=base/(n+".sqlite");assert sha(f)==v["sha"] and f.stat().st_size==v["bytes"]
            with sqlite3.connect(f) as db:assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    out={f:sha(D/f) for f in FILES};path=D/"manifest.json"
    if args.seal and not path.exists():save(path,out)
    assert read(path)==out;print("verified",len(out),sha(path))
if __name__=="__main__":main()

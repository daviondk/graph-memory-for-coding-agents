"""Check full source, independent extension, exact evidence and physical databases."""
import argparse
import sqlite3
from pathlib import Path
from prepare import D,P,save,read,sha
PRIMARY=("PROTOCOL_RU.md","prepare.py","plan.json","source-inventory.json.gz","source-cost.json.gz","source-seal.json","study.py","per-session.json.gz","construction-cost.json.gz","primary-events.json.gz","result-seal.json","primary-sql.json.gz","physical-seal.json","summarize.py","results.json","REPORT_RU.md","verify.py")
EXTRA=("PROTOCOL_RU.md","repeat.py","extension-plan.json","plan.json","source-inventory.json.gz","source-cost.json.gz","source-seal.json","per-session.json.gz","construction-cost.json.gz","primary-events.json.gz","result-seal.json","extension-results.json")
def main():
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");p.add_argument("--private",action="store_true");opt=p.parse_args()
    r=read(D/"results.json");x=read(D/"alias4/extension-results.json")["estimates"]["new/overlap3"];main=r["groups"]["overlap3"]["line_bm25"]["arms"]
    assert r["exhaustive_validations"]==744400 and r["attainable_answer_checks"]==29776 and main["mask_pareto4"]["sampled"]["certified"]==4176
    assert x["sessions"]==11 and x["comparisons"]["mask_group"]["certified"]==[690,677]
    if opt.private:
        for pub,root in ((D,P),(D/"alias4",Path("D:/CodexResearch/x20-r31-isetrace-dependencies-alias4"))):
            base=root/sha(pub/"plan.json")
            assert sha(base/"input.json.gz")==read(pub/"source-seal.json")["private_input"]
            for n,row in read(pub/"result-seal.json")["physical"].items():
                f=base/"physical"/(n+".sqlite");assert sha(f)==row["sha"] and f.stat().st_size==row["bytes"]
                with sqlite3.connect(f) as db:assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
    values={n:sha(D/n) for n in PRIMARY}
    values.update({"alias4/"+n:sha(D/"alias4"/n) for n in EXTRA})
    path=D/"manifest.json"
    if opt.seal and not path.exists():save(path,values)
    assert read(path)==values;print("verified",len(values),sha(path))
if __name__=="__main__":main()

"""Validate portable evidence and linked upstream inputs; optionally verify the private SQLite data."""
import argparse
from pathlib import Path
from design import HERE,UP,PRIVATE,read,save,sha

FILES=["PROTOCOL_RU.md","design.py","plan.json","study.py","analyze.py","verify.py","REPORT_RU.md",
       "reference.json.gz","build-rows.json.gz","build-seal.json","measurements.json.gz","measurement-seal.json","results.json"]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seal",action="store_true");p.add_argument("--private",action="store_true");args=p.parse_args()
    result=read(HERE/"results.json");b=read(HERE/"build-seal.json");m=read(HERE/"measurement-seal.json")
    assert len(read(HERE/"plan.json")["qids"])==result["questions"]==96
    assert result["strict_comparisons"]==result["validated_queries"]*4==8808
    assert result["cross_checked_upstream"]==288 and result["db"]["sky"]["standalone_entries"]==3059
    assert m["samples"]==9216 and m["build"]==sha(HERE/"build-seal.json") and b["code"]==sha(HERE/"study.py")
    assert b["reference"]==sha(HERE/"reference.json.gz") and b["input"]==sha(UP/"forecast-seal.json")
    if args.private:
        base=PRIVATE/sha(HERE/"plan.json")
        for n,data in b["databases"].items():assert sha(base/(n+".sqlite"))==data["sha256"]
    value={p:sha(HERE/p) for p in FILES}
    dest=HERE/"manifest.json"
    if args.seal and not dest.exists():save(dest,value)
    assert read(dest)==value
    print("verified",len(value),sha(dest))
if __name__=="__main__":main()

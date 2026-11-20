"""Collect anonymous, pre-change source. This process receives no evaluation labels."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import gzip,hashlib,json,sys
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent
R=D.parent
sys.path.insert(0,str(R/"grounding"))
import acquire
def main():
    predictions=[json.loads(l) for l in (R/"input/orca.jsonl").read_text().splitlines()]
    assert len(predictions)==len({r["instance_id"] for r in predictions})==50
    original=R.parents[1]/"sota_round/coding/verified.parquet"
    items={i["instance_id"]:i for i in pq.read_table(original,columns=["instance_id","repo","base_commit","problem_statement","created_at"]).to_pylist()}
    records=[]
    for p in predictions:
        i=p["instance_id"];q=items[i]
        is_excluded=bool(acquire.DENY.search(q["problem_statement"]))
        records.append(dict(id=i,repo=q["repo"],base=q["base_commit"],date=str(q["created_at"]),source="orca",
                            question="" if is_excluded else q["problem_statement"],paths=list(dict.fromkeys(p["found_files"]))[:5],excluded=is_excluded))
    with ThreadPoolExecutor(4) as ex:maps=list(ex.map(acquire.slates,records))
    needed={}
    for r,m in zip(records,maps):
        r["blobs"]=m
        for path,oid in m.items():
            if not (R/"grounding/sources"/(oid+".gz")).exists():needed.setdefault(r["repo"],{})[oid]=(r["base"],path)
    with ThreadPoolExecutor(3) as ex:receipts=list(ex.map(acquire.objects,sorted(needed.items())))
    (D/"inputs.json.gz").write_bytes(gzip.compress(json.dumps(records).encode(),mtime=0))
    def sh(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    hashes={p.name:sh(p) for p in [D/"PROTOCOL.md",R/"grounding/coefficients.json.gz",R/"grounding/features.py",
                                   R/"input/orca.jsonl",D/"inputs.json.gz",D/"predict.py",D/"score.py"]}
    meta={"hashes":hashes,"missing_receipts":receipts,"issues":len(records),"paths":sum(len(r["paths"]) for r in records),
          "resolved_paths":sum(len(r["blobs"]) for r in records)}
    (D/"design_lock.json").write_text(json.dumps(meta,indent=2),encoding="utf8")
    print(meta)
if __name__=="__main__":main()


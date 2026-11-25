"""Inspect types, field names and sizes without printing conversation text."""
from pathlib import Path
import json,pyarrow.parquet as pq
P=Path("D:/CodexResearch/x20-r28-retraction");LM=Path("D:/CodexResearch/x20-longmemeval-dretr/longmemeval_s_cleaned.json")
def schema(obj,max_depth=4):
    if isinstance(obj,list):return ["length="+str(len(obj))]+([schema(obj[0],max_depth-1)] if obj and max_depth else [])
    if isinstance(obj,dict):return {str(k):schema(v,max_depth-1) if max_depth else type(v).__name__ for k,v in list(obj.items())[:32]}
    return type(obj).__name__
def main():
    a=json.loads((P/"halumem-medium.jsonl").open(encoding="utf8").readline());print("HALU",json.dumps(schema(a,5))[:4000])
    s=json.loads((P/"stale.json").read_bytes());print("STALE",json.dumps(schema(s,6))[:4900]);del s
    m=json.loads(LM.read_bytes());upd=next(r for r in m if r["question_type"]=="knowledge-update");print("LME",len(m),json.dumps(schema(upd,4))[:1800]);del m
    f=pq.read_table(P/"fact.parquet").to_pylist();print("MAB",len(f),json.dumps(schema(f[0],5))[:2500])
    print("metadata sources",[(r.get("metadata",{}).get("source"),len(r.get("questions",[])),len(r.get("context",""))) for r in f])
if __name__=="__main__":main()


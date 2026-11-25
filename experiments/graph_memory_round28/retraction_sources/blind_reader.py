"""Return exactly one question and its original source history; no access to evaluator/ or other queries in payload."""
from pathlib import Path
import argparse,gzip,json
def read_one(root,qid):
    questions=json.loads((root/"questions.json").read_bytes())
    q=next(v for v in questions if v["qid"]==qid)
    h=json.loads(gzip.decompress((root/"history"/(q["case"]+".json.gz")).read_bytes()))
    return dict(qid=qid,question=q["question"],sources=h["sources"])
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("qid");p.add_argument("--root",type=Path,default=Path("D:/CodexResearch/x20-r28-retraction/stale-projection"))
    args=p.parse_args();print(json.dumps(read_one(args.root,args.qid),ensure_ascii=False))


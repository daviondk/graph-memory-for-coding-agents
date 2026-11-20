import sys,time,os
from concurrent.futures import ProcessPoolExecutor
import predict,grade
from context import D,read,save,h,json,gzip,atomic_line
R=D/"replication"
def emit(n,x):(R/n).write_text(json.dumps(x,indent=1))
def pred(k):
    predict.D=R
    return predict.one(k)
def grade_rep(k):
    grade.D=R
    return grade.case(k)
def main():
    phase=sys.argv[1]
    if phase=="predict":
        files=[D/"predict.py",D/"context.py",D/"fine_model.json",D/"EXPANSION_PROTOCOL.md",D/"confirm_acquire.py",D/"replicate.py",R/"selection.json",R/"source_receipt.json",*sorted(R.glob("source_*.gz"))]
        emit("method_lock.json",{str(f):h(f) for f in files})
        with ProcessPoolExecutor(4) as pool:counts=list(pool.map(pred,range(8)))
        emit("prediction_lock.json",{"counts":counts,"files":{p.name:h(p) for p in [R/"method_lock.json",*sorted(R.glob("pred_*.gz"))]}})
    if phase=="grade":
        assert all(h(R/n)==s for n,s in json.loads((R/"prediction_lock.json").read_bytes())["files"].items())
        with ProcessPoolExecutor(4) as pool:data=list(pool.map(grade_rep,range(8)))
        rows=[r for records,n,c in data for r in records]
        with gzip.open(R/"scored.jsonl.gz","wt",encoding="utf8",compresslevel=3) as f:
            for r in rows:atomic_line(f,r)
        out={str(b):grade.metrics([r for r in rows if r[2]==b]) for b in grade.BUDGETS}
        emit("results.json",dict(token_checks=sum(x[2] for x in data),cuts=sum(x[1] for x in data),budget=out))
if __name__=="__main__":main()

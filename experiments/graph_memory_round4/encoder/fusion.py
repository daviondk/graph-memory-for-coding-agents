from collections import defaultdict
from fractions import Fraction
from common_run import D,R,hashfile,load,readgz,save,now,writegz

assert hashfile(D/"predictions.jsonl.gz")==load(D/"prediction_lock.json")["pred_sha"]
assert hashfile(R/"strict_java.pred.jsonl.gz")==load(R/"strict_graph_lock.json")["sha256"]
neural={(r["panel"],r["idx"],int(r["query"])):r["rank"] for r in readgz(D/"predictions.jsonl.gz") if r["query"] in ("3","10")}
rows=[]
for panel,i,k,project,size,h,e,arms in readgz(R/"strict_java.pred.jsonl.gz"):
    key=panel,i,k
    if key not in neural:
        continue
    G,U=arms["graph"],neural[key]
    assert set(G)==set(U)==set(range(len(G)))
    r1={x:r for r,x in enumerate(G,1)}
    r2={x:r for r,x in enumerate(U,1)}
    combined=sorted(range(len(G)), key=lambda x:-(Fraction(1,r1[x])+Fraction(1,r2[x])))
    rows.append([panel,i,k,combined])
assert len(rows)==640
writegz(D/"fusion.pred.jsonl.gz",rows)
save("fusion_decision_lock.json",dict(utc=now(),pred_sha=hashfile(D/"fusion.pred.jsonl.gz"),code_sha=hashfile(D/"fusion.py"),plan_sha=hashfile(D/"FUSION_PROTOCOL_RU.md")))

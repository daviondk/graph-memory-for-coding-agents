"""Prepare opaque blocks and independently classify all applicable signed edit receipts."""
from pathlib import Path
import json,gzip,hashlib,sys

D=Path(__file__).resolve().parent
W=D.parents[1]
S=D.parent/"span_updates";P=D.parent/"natural_invalidations"
REV="5508f8be81025d8aa90726b1e06aef4ea484e577"


def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)


def digest(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def h(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def save(name,value):
    raw=(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
    dest=D/name
    dest.write_bytes(gzip.compress(raw,mtime=0) if dest.suffix==".gz" else raw)


def main():
    p=S/"scored.json.gz";a=S/"audit_strict_rows.json.gz";n=P/"plans.json.gz"
    assert digest(p)==read(S/"results.json")["forecasts"]==read(S/"audit_strict.json")["sealed"]
    assert digest(a)==read(S/"audit_strict.json")["checks"]
    assert any(digest(n)==v for v in read(P/"manifest.json").get("files",{}).values()) or digest(n) in (P/"manifest.json").read_text()
    strict={(rid,receipt):counts for rid,receipt,counts in read(a)}
    plans=read(n);output={};grades={}
    for row in read(p):
        rid=row["rid"];receipt=row["receipt"];event=row["event"]
        ck=h(rid+"|"+str(receipt));estimate=strict[rid,receipt];old=row["old"]
        assert old and estimate["confirmed_delta"]==1
        before=plans[rid][str(event)]
        selected=[dict(slot=i,path=before[i][0],low=before[i][1],high=before[i][2],bytes=before[i][3]) for i in old]
        assert all(len(b["path"])==64 and b["bytes"]>=0 for b in selected)
        output[ck]=dict(group=row["group"],changed=row["path"],chosen=selected,issue=h(row["issue"]))
        mismatch=estimate.get("reused_selected_post_mismatch",0)
        grades[ck]=dict(file_reuse=int(row["file_reuse"]),range_reuse=int(row["range_reuse"]),
                        strict_range=int(row["range_reuse"] and mismatch==0),reused_selected_post_mismatch=mismatch)
    assert len(output)==2696
    rank=sorted(output,key=lambda k:h("r40-memtrace-adapter/"+k))
    pilot=[k for g in ("main","additional") for k in [v for v in rank if output[v]["group"]==g][:32]]
    assert len(pilot)==64
    save("cases.json.gz",output);save("comparison-reference.json.gz",grades)
    save("panel.json",dict(pilot=pilot,other=[k for k in rank if k not in set(pilot)]))
    fns=["PROTOCOL_RU.md","project.py","cases.json.gz","comparison-reference.json.gz","panel.json","upstream-tree.json","source-hashes.json"]
    save("input-seal.json",dict(files={k:digest(D/k) for k in fns},
                               source={src.relative_to(W).as_posix():digest(src) for src in (p,a,n)},
                               upstream=REV))
    print("Prepared",len(output),"real edits, 64 fixed pilot transactions, all payloads anonymized.")

if __name__=="__main__":main()

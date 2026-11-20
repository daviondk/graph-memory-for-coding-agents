"""Offline verification of every label, prediction, opening and paired trial in this folder."""
import gzip,hashlib,json,math
from pathlib import Path
D=Path(__file__).resolve().parent
def load(n):
    p=D/n;b=p.read_bytes()
    if n.endswith(".jsonl"):return [json.loads(v) for v in b.splitlines()]
    return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    for lock in ("assignment.json","action-lock.json","read-lock.json"):
        f=load(lock)
        for name,sha in f.get("files",f).items():assert h(D/name)==sha
    pr={r["iid"]:r for r in load("patch_labels.gz")};nav=load("navigation_labels.gz")
    a={(r["id"],r["method"]):r for r in load("model.jsonl")}
    rr={(r["id"],r["arm"]):r for r in load("reads.gz")}
    ver={(r["id"],r["arm"]):r for r in load("git_receipt_verification.json")}
    cases=load("cases.gz");score={r["id"]:r for r in load("outcomes.gz")};result=load("results.json")
    assert set(ver)=={key for key,r in rr.items() if r["opened"]}
    answers={}
    for c in cases:
        r=pr[c["iid"]];m=score[c["id"]];opts={p["path"] for p in c["menu"]}
        qualified=r.get("status")=="ok" and r["parent"]==c["base"] and r["old_time"]<=r["new_time"] and bool(r["prod"])
        assert qualified==(m["status"]=="eligible")
        for arm in ("named","pair","recommend","none"):
            k=c["id"],arm;ob=rr[k];model=a[k];ch=ob["path"] if ob["opened"] else None;s=m["arms"][arm]
            assert s["path"]==ch and ch==model["path"] if ob["opened"] else s["path"] is None
            if ob["opened"]:assert ch in opts and ob["blob"]==ver[k]["sha256"] and ob["bytes"]==ver[k]["nbytes"]
            assert s["patch"]==(ch in r["prod"] if qualified else None)
            truth=nav[c["id"]]["target"];assert s["navigation"]==(ch==truth["path"] if truth else None)
            answers[k]=s
    for pair,parts in result["pairs"].items():
        aa,bb=pair.split("-")
        for end in ("patch","navigation"):
            dif=[int(v[end])-int(answers[i,bb][end]) for (i,k),v in answers.items() if k==aa and v[end] is not None]
            rec=parts[end];assert [len(dif),dif.count(1),dif.count(-1),dif.count(0)]==[rec["n"],rec["wins"],rec["losses"],rec["ties"]]
    print(len(cases),"tasks,",len(answers),"decisions,",len(ver),"verified Git blobs by arm; raw outcomes and paired counts agree")
if __name__=="__main__":main()

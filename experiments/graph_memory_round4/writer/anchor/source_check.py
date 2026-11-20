"""Confirm whether the underlying public log recorded a source change in the grading lookahead window."""
import hashlib,json,urllib.request
from run_anchor import B,HERE,read,save
def main():
    example=read(HERE/"independent_targets.json")["mismatches"][0]
    r=next(x for x in read(B/"receipts.json") if x["id"]==example["issue"])
    with urllib.request.urlopen(urllib.request.Request(r["url"],headers={"User-Agent":"memory-anchor-audit"}),timeout=40) as f:
        data=f.read()
    assert hashlib.sha256(data).hexdigest()==r["source_sha256"]
    steps=json.loads(data)["trajectory"];t=example["t"]
    actions=[(i+1,steps[i]["action"]) for i in range(t,min(len(steps),t+3))]
    # Record only the action classification and a digest. No source action is executed.
    recorded=[dict(event=i,row_sha256=hashlib.sha256(a.encode()).hexdigest(),
        kind="checkout restoration of source files" if "git reset --hard HEAD" in a else "editor literal replacement" if "str_replace_editor str_replace" in a else "other") for i,a in actions]
    assert any(q["kind"].startswith("checkout restoration") for q in recorded)
    save(HERE/"source_check.json",dict(id=r["id"],url=r["url"],sha=hashlib.sha256(data).hexdigest(),measurement_cut=t,actions=recorded))
if __name__=="__main__":main()

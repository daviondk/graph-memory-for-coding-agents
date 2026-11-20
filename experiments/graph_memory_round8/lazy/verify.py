"""Independent integrity and prefix tests. Run after scoring."""
from collections import Counter
import json
from extract import ROOT, digest, rows, write_json
from replay import Memory

def main():
    for name,wrapped in [("inputs.json",True),("lock.json",True),("results_lock.json",True),("ablation_lock.json",False)]:
        lock=json.loads((ROOT/name).read_bytes())
        for file,value in (lock["files"] if wrapped else lock).items():
            assert digest(ROOT/file)==value,(name,file)
    inputs=json.loads((ROOT/"inputs.json").read_bytes())
    for rel,val in inputs["sources"].items():
        assert digest(ROOT.parents[1]/rel)==val,rel
    by_id={q["id"]:q for q in rows(ROOT/"observations.gz")}
    stored={(f["id"],f["cap"],f["t"]):f for f in rows(ROOT/"forecasts.gz") if f["t"]>=0}
    sample_count=0
    for (iid,cap,t),rec in stored.items():
        q=by_id[iid]
        # Replay from scratch through t-1; make future and current outputs inaccessible.
        sub=Memory(cap)
        for event in q["events"][:t]:
            sub.advance(event)
        path,limits=q["requests"][t]
        pointers,anchors,seen=sub.forecast(path,iid,t)
        assert (pointers,anchors,seen)==(rec["pointers"],rec["anchors"],rec["resident"])
        if limits:
            assert tuple(sub.codec(path,limits))==(rec["sizes"],rec["codes"])
        sample_count+=1
    ctr=Counter()
    for s in rows(ROOT/"scores.gz"):
        c=s["cap"];p=s["panel"]
        ctr[p,c,"n"]+=1
        ctr[p,c,"first"]+=s["hit"][2]
        if s["sizes"]:
            assert all(a>=b for a,b in zip(s["sizes"],s["sizes"][1:]))
            ctr[p,c,"multi"]+=s["sizes"][-1]
    for key,v in json.loads((ROOT/"results.json").read_bytes()).items():
        p,c=key.split("/");c=int(c)
        assert (ctr[p,c,"n"],ctr[p,c,"first"],ctr[p,c,"multi"])==(v["n"],v["hit"]["first"],v["bytes"]["multi"])
    write_json("verification.json",dict(verified_sources=len(inputs["sources"]),prefixes_checked=sample_count,
                primary_panels=3,caps=[128,512],verifier_sha256=digest(ROOT/"verify.py")))


if __name__=="__main__":
    main()

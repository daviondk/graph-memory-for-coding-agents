"""Independent byte/character address checks and complete randomized-block inventory."""
from collections import Counter
import sqlite3
from cfg import *
def main():
    freeze();b=load(D/"build.json");assert b["db"]==sha_file(DB) and b["cases"]==sha_file(D/"cases.json.gz")
    db=sqlite3.connect(DB.as_uri()+"?mode=ro&immutable=1",uri=True);assert db.execute("pragma integrity_check").fetchone()==("ok",)
    fields=dict(db.execute("select rid,body from field"));positions=0
    for rid,c,byte in db.execute("select rid,c,b from checkpoint order by rid,c"):
        assert byte==len(fields[rid][:c].encode());positions+=1
    assert positions==b["checkpoint_rows"]
    cases=load(D/"cases.json.gz")
    for r in cases:
        body=fields[r["rid"]];raw=body.encode();assert len(raw)==r["field_bytes"]
        for v in r["both"]+[r["right"]]:
            sub=body[v["l"]:v["h"]].encode();assert sub==raw[v["b"]:v["z"]] and sha(sub)==v["sha"] and len(sub)==v["bytes"]
        assert sha(b"\n".join(v["header"].encode()+raw[v["b"]:v["z"]] for v in r["both"]))==r["wire"]
    db.close();low=load(D/"measurements.json.gz");a=load(D/"measurement-seal.json");assert a["slices"]==sha_file(D/"measurements.json.gz") and a["traffic"]==sha_file(D/"interface.json.gz")
    got=Counter((r[0],r[1],r[2]) for r in low);assert len(low)==62208 and len(got)==24*288 and set(got.values())=={9}
    assert len({(s,i,j,k) for s,i,j,k,t,b in low})==len(low)
    assert sha_file(D/"online-times.json.gz")==load(D/"online-results.json")["raw"]
    assert sha_file(D/"matched-times.json.gz")==load(D/"matched-results.json")["raw"]
    online=load(D/"online-times.json.gz");assert len(online)==5*6*len(cases) and len({(s,i,j,k) for s,i,j,k,*_ in online})==len(online)
    matched=load(D/"matched-times.json.gz");assert len(matched)==2*9*len(cases) and len({(i,j,k) for i,j,k,*_ in matched})==len(matched)
    result={"cases":len(cases),"fields":len(fields),"encoded_coordinates":len(cases)*6,"checkpoint_values":positions,"warm_and_fresh":len(low),"online":len(online),"matched_online":len(matched),
       "source":sha_file(D/"build.json"),"results":sha_file(D/"results.json"),"full_service":sha_file(D/"online-results.json"),"matched":sha_file(D/"matched-results.json")}
    f=D/"verification.json"
    if f.exists():assert load(f)==result
    else:save(f,result)
    print(result)
if __name__=="__main__":main()

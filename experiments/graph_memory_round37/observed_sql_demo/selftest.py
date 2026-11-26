"""Test actual readers against independent frozen materialized values."""
from contextlib import contextmanager
from hashlib import sha256
import json, random, sqlite3, threading
from urllib.parse import urlencode
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from serve import D,dbpair,catalogue,digest,endpoint,service
def sha(p):return sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n",encoding="utf-8")
@contextmanager
def running():
    with service() as s:
        t=threading.Thread(target=s.serve_forever,kwargs={"poll_interval":.04});t.start()
        try:yield f"http://127.0.0.1:{s.server_port}"
        finally:s.shutdown();t.join(3);assert not t.is_alive()
def main():
    oracles=json.loads((D/"test-oracle.json").read_bytes())
    dbs=[D/"eager.db",D/"inverse.db"];before=[sha(p) for p in dbs]
    with dbpair() as stores:
        cats=catalogue(stores[1])
        for store in stores:
            assert store.execute("PRAGMA query_only").fetchone()==(1,)
            try:store.execute("CREATE TABLE demo_test(z)")
            except sqlite3.OperationalError as e:assert "readonly" in str(e).lower()
            else:raise AssertionError("Writable SQLite connection")
    tests=0; pres={}; classes=set()
    rng=random.Random(370244)
    for key,c in cats.items():
        fixture=oracles[key];reference=fixture["oracle"]; q={"case":[key]}
        src=endpoint("/api/source",q); coords=[v[0] for v in src["base"]+src["receipt"]+reference]+[src["start"],src["end"]]
        lo=max(1,min(coords)-1);hi=max(coords)+1
        windows={(v,v) for v in range(lo,hi+1)}|{tuple(c["requested"]),tuple(c["special"]),(1,1),(99999,100000)}
        for _ in range(75):
            x=rng.randint(lo,hi);windows.add((x,min(hi,x+rng.randrange(60))))
        for a,b in sorted(windows):
            x=endpoint("/api/read",q|{"lo":[str(a)],"hi":[str(b)]})
            truth=[(n,bytes.fromhex(s)) for n,s in reference if a<=n<=b]
            assert [(r["n"],r["hash"]) for r in x["rows"]]==[(n,s.hex()) for n,s in truth]
            actual={r["n"] for r in x["rows"]};missing=[]
            for v in x["gaps"]:
                missing.extend(range(v["lo"],v["hi"]+1)); classes.add(v["reason"])
                if v["reason"]=="evicted":assert set(range(v["lo"],v["hi"]+1))<=set(fixture["retention_omissions"])
            assert sorted(missing)==sorted(set(range(a,b+1))-actual)
            assert {r["answer_digest"] for r in x["stats"].values()}=={digest(truth)}
            if [a,b]==c["requested"]:
                for name,r in x["stats"].items():assert r["db_rows"]==fixture["default"][name]["returned"]
                pres[key]=dict(range=[a,b],retained=len(truth),rows={n:v["db_rows"] for n,v in x["stats"].items()},
                    overflow=x["overflow"],special=c["special"],baseline=fixture["actual_observed"],digest=digest(truth))
            tests+=1
    errors=0
    with running() as url:
        for suffix,expected in [("/api/cases",200),("/api/read?case=growth&lo=1&hi=512",200),
          ("/api/read?case=growth&lo=1&hi=513",400),("/api/read?case=x&lo=1&hi=2",400),
          ("/api/read?case=growth&lo=3&hi=2",400),("/api/read?case=growth&lo=0&hi=1",400),
          ("/api/read?case=growth&lo=1",400),("/api/read?case=growth&lo=1&hi=100001",400),
          ("/api/read?case=growth&lo=1&lo=2&hi=2",400),("/api/read?case=growth&lo=1.5&hi=2",400),
          ("/api/source?case=growth&extra=x",400),("/inverse.db",404),("/test-oracle.json",404)]:
            try:
                with urlopen(url+suffix) as f:status=f.status
            except HTTPError as e:status=e.code
            assert status==expected,(suffix,status);errors+=int(status>=400)
        try:urlopen(Request(url+"/api/read",method="POST",data=b""))
        except HTTPError as e:assert e.code==501
        else:raise AssertionError("POST route should not exist")
    assert classes=={"unobserved","evicted","replaced"} and [sha(p) for p in dbs]==before
    assert not any(D.glob("*.db-*"))
    out=dict(ranges=tests,cases=pres,invalid_http_rejected=errors+1,
             gap_reasons=sorted(classes),databases_sha256=before,sqlite=sqlite3.sqlite_version)
    write(D/"checks.json",out);print(json.dumps(out))
if __name__=="__main__":main()

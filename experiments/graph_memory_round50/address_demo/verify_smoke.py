"""Offline check of all endpoints and replayed addresses, with optional full archive parity."""
import argparse,gzip,hashlib,json,sqlite3,subprocess,sys
from collections import Counter
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from urllib.parse import urlencode
from address_server import ROOT,database,detail

def get(path):
    with urlopen(path,timeout=5) as response:return json.load(response)
def main():
    cli=argparse.ArgumentParser();cli.add_argument("--study",type=Path);args=cli.parse_args()
    if (ROOT/"manifest.json").exists():
        sig=json.loads((ROOT/"manifest.json").read_bytes())["files"]
        for name,h in sig.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    with closing(database()) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        ids=[r[0] for r in db.execute("SELECT id FROM episode ORDER BY id")]
        assert len(ids)==1280 and db.execute("SELECT count(*) FROM candidate").fetchone()[0]==11520
        assert db.execute("SELECT count(*) FROM response").fetchone()[0]==1580
        canonical=None
        if args.study:
            load=lambda name:json.loads(gzip.decompress((args.study/name).read_bytes()))
            canonical={hashlib.sha256(k.encode()).hexdigest()[:16]:v for k,v in load("orders.json.gz").items()}
            refs={hashlib.sha256(k.encode()).hexdigest()[:16]:v for k,v in load("contexts.json.gz").items()}
            predictions=load("answers.json.gz");out={hashlib.sha256(k.encode()).hexdigest()[:16]:v for k,v in load("outcomes.json.gz").items()}
            assert {k for k in canonical}==set(ids)
        switches=Counter();gains=Counter();sums=Counter()
        for q in ids:
            for mode,arm in [("0","dense"),("registered","adaptive"),("always","linked_dense")]:
                v=detail(db,q,mode);a=v["selected_answer"];base=v["baseline_answer"]
                assert a and base and len(v["candidates"])==9 and v["snapshot"]==a["snapshot"]
                if canonical:
                    i,k,n=refs[q]["refs"][arm]
                    assert v["selected"]==i==canonical[q][arm] and a["prompt_sha"]==k and a["input_tokens"]==n
                    assert a["answer"]==predictions[k]["answer"] and a["f1"]==out[q]["arms"][arm][1]
                switches[mode]+=int(v["changed"]);sums[mode]+=a["f1"]
                if mode=="registered":gains["gain" if a["f1"]>base["f1"] else "loss" if a["f1"]<base["f1"] else "tie"]+=1
        assert [switches[m] for m in ["0","registered","always"]]==[0,55,300]
        assert [round(sums[m]*100/len(ids),2) for m in ["0","registered","always"]]==[41.62,42.70,42.58]
        assert gains==dict(gain=21,loss=4,tie=1255)
    proc=subprocess.Popen([sys.executable,"-B",str(ROOT/"address_server.py"),"--port","0"],stdout=subprocess.PIPE,text=True)
    try:
        url=proc.stdout.readline().strip();assert url.startswith("http://127.0.0.1:")
        with urlopen(url,timeout=5) as response:assert b"Address selection" in response.read()
        assert get(url+"api/health")["count"]==1280
        for tag in ["all","switched","gain","loss"]:
            case=get(url+"api/cases?"+urlencode({"filter":tag,"limit":1}))
            assert case["total"]=={"all":1280,"switched":55,"gain":21,"loss":4}[tag]
        q=case["items"][0]["id"];path=url+"api/case?id="+q
        v=get(path);assert v["selected_answer"]["f1"]<v["baseline_answer"]["f1"]
        assert "gold" not in v and "aliases" not in v and "supports" not in v
        assert get(path+"&prompt=missing")["selected_answer"] is None
        v=get(path+"&snapshot=missing");assert v["baseline_answer"] is None and v["selected_answer"] is None
        assert get(url+"api/gold?id="+q)["aliases"]
        for path,code in [("api/case?id=x",404),("api/cases?filter=bad",400),("api/case?id="+q+"&threshold=nan",400)]:
            try:get(url+path);raise AssertionError(path)
            except HTTPError as e:assert e.code==code
    finally:proc.terminate();proc.wait(timeout=5)
    print("OK: 3840 exact selections, 1280 episodes, 11520 candidates, 1580 prompts, 3 threshold modes and HTTP safeguards.")
if __name__=="__main__":main()


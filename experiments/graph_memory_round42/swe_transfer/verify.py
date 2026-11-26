"""Verify the public, hashed replay without private work trees or model inference."""
from pathlib import Path
from collections import Counter
from hashlib import sha256
import gzip,json
D=Path(__file__).resolve().parent
def load(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def main():
    s=load(D/"forecast-seal.json");raw=D/"forecasts.json.gz"
    assert sha256(raw.read_bytes()).hexdigest()==s["rows"]
    assert sha256((D/"transfer.py").read_bytes()).hexdigest()==s["program"]
    p=load(raw);a=load(D/"audit.json.gz");r=load(D/"results.json")["all"]
    assert set(p)==set(a) and len(p)==265
    assert len({z["issue"] for z in p.values()})==r["issues"]==159
    for m in ("file","range","edges","local"):
        total=Counter(same=0,receipt_checks=0,receipt_errors=0,future_checks=0,future_errors=0)
        for k,z in p.items():
            total["same"]+=int(z["sel"][m]==z["old"])
            if not z["anchored"]:assert z["sel"][m]==z["sel"]["file"]
            for src,(n,errors) in a[k]["per"][m].items():
                assert 0<=errors<=n<=len(z["maps"][m])
                total[src+"_checks"]+=n;total[src+"_errors"]+=errors
        assert dict(total)==r["methods"][m]
    assert (r["wins"],r["losses"])==(2,0)
    print("265 matched edits, 159 distinct tasks, four policies verified")
if __name__=="__main__":main()

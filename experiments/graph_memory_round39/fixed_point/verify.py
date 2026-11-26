import gzip,json,hashlib
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    s=read(D/"seal.json");r=read(D/"benchmark.json");w=read(D/"withdrawals.json")
    assert sha(D/"seal.json")==r["seal"] and s["code"]==sha(D/"precision.py") and s["cpp"]==sha(D/"integer.cpp")
    aggregate={b:0 for b in ("8","16","32")}
    for key,rc in s["seeds"].items():
        p=D/f"test-{key}-pred.json.gz";assert sha(p)==rc["sha"]
        ours=read(p);original=read(D.parent/f"global_packet/test-{key}-pred.json.gz")
        for b in aggregate:
            changes=sum(v[1][b]!=original[q][1]["graph-dp"] for q,v in ours.items());assert changes==r["seeds"][key][b]["changed"];aggregate[b]+=changes
    assert w["total"]==sum(v[0] for row in w["rows"].values() for v in row.values())
    assert w["float_same"]==sum(v[1] for row in w["rows"].values() for v in row.values())
    assert w["certified_unchanged"]==sum(v[2] for row in w["rows"].values() for v in row.values())
    if (D/"manifest.json").exists():
        for k,h in read(D/"manifest.json")["files"].items():assert sha(D/k)==h
    print(aggregate,w["total"],w["float_same"])
if __name__=="__main__":main()


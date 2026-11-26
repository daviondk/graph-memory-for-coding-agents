"""Offline integrity, read-demand scores, transaction-depth totals and physical capacity checks."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,json,hashlib
D=Path(__file__).resolve().parent
def read(n):
    p=D/n;b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(n):return hashlib.sha256((D/n).read_bytes()).hexdigest()
def main():
    f=read("forecast-seal.json");s=read("summary.json")["all"];a=read("capacity-audit.json");g=read("grade-seal.json")
    assert f["forecasts"]==sha("forecasts.json.gz") and g["rows"]==sha("outcomes.json.gz")
    assert f["program"]==sha("transact.py") and f["input"]==sha("input-seal.json") and f["protocol"]==sha("PROTOCOL_RU.md")
    p=read("forecasts.json.gz");o=read("outcomes.json.gz");assert set(p)==set(o) and len(o)==2696
    agg=defaultdict(Counter);demand=defaultdict(Counter);depth=read("depth-summary.json")
    for k,r in p.items():
        for n,v in r["arms"].items():
            lim=n.rsplit("_",1)[1];wire,nr,nb,sz,_=v["wire"];assert wire==8+nr*50+nb*2+sz
            if lim!="unlimited":assert wire<=f["writer_peak"][n]<=int(lim)
            age=dict(zip(v["all"],v["depth"],strict=True));assert len(age)==len(v["all"]) and set(v["read"])<=set(age)
            for t in ("read","all"):
                idx=v[t];ck=o[k]["checks"];out=o[k]["arms"][n][t]
                assert int(any(ck[j][1] and ck[j][2] for j in idx))==out["hit"]
                assert sum(ck[j][1]*ck[j][2] for j in idx)==out["novel_lines"]
                assert sum(not ck[j][1] for j in idx)==out["bad_new"] and sum(not ck[j][0] for j in idx)==out["bad_old"]
                assert sum(r["candidates"][j][3]+1 for j in idx)==out["raw_bytes"]
                if t=="read":assert out["raw_bytes"]==v["emitted_bytes"]<=2048
                agg[n,t].update(out)
                for j in idx:
                    z=str(min(2,age[j]));demand[n,t]["candidates_depth"+z]+=1;demand[n,t]["demand_depth"+z]+=ck[j][1]*ck[j][2]
    for n,val in s["arms"].items():
        for t in ("read","all"):
            assert dict(agg[n,t])==val[t] and dict(demand[n,t])==depth["counts"][n][t]
    for n,v in a["counts"].items():
        assert v["snapshots"]==f["counts"][n]["pending"] and v["total_escrow_bytes"]==f["counts"][n]["escrow_bytes_sum"] and v["peak"]<=f["writer_peak"][n]
    if (D/"manifest.json").exists():assert all(sha(n)==h for n,h in read("manifest.json")["files"].items())
    print("Verified",len(p),"edits,",len(s["arms"]),"writer policies, all readback outcomes, depth counts and capacity accounts.")
if __name__=="__main__":main()

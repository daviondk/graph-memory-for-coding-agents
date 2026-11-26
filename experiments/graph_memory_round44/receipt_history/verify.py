"""Independent, standard library replay of every stored packet count and its matched previous baseline."""
from pathlib import Path
import gzip,hashlib,json
D=Path(__file__).resolve().parent;old=D.parent/"history_writer"
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    f=read(D/"forecast-seal.json");g=read(D/"grade-seal.json");s=read(D/"summary.json")["all"]
    assert f["forecasts"]==sha(D/"forecasts.json.gz") and g["rows"]==sha(D/"outcomes.json.gz") and g["forecasts"]==sha(D/"forecast-seal.json")
    assert f["protocol"]==sha(D/"PROTOCOL_RU.md") and f["controls"]==sha(old/"forecasts.json.gz")
    p=read(D/"forecasts.json.gz");orig=read(old/"forecasts.json.gz");o=read(D/"outcomes.json.gz")
    assert len(p)==len(orig)==len(o)==2696 and p.keys()==orig.keys()==o.keys()
    data={m:{a:[0,0,0] for a in ("read","all")} for m in s["arms"]}
    for k,row in p.items():
        mat=o[k]["checks"];assert len(mat)==len(row["candidates"])
        for m,ar in row["arms"].items():
            n=m.partition("_")[2];w=ar["wire"];assert w[0]==8+50*w[1]+2*w[2]+w[3]
            if n!="unlimited":assert w[0]<=f["peak_wire"][m]<=int(n)
            if m.startswith("views_"):
                ori=orig[k]["arms"]["lru_"+n];assert w==ori["wire"]
                for t in ("read","all"):assert [row["candidates"][i] for i in ar[t]]==[orig[k]["candidates"][i] for i in ori[t]]
            assert len(set(ar["all"]))==len(ar["all"]) and set(ar["read"])<=set(ar["all"])
            for t in ("read","all"):
                ids=ar[t];rec=o[k]["arms"][m][t]
                assert sum(mat[j][1]*mat[j][2] for j in ids)==rec["novel_lines"]
                assert sum(not mat[j][1] for j in ids)==rec["bad_new"]
                assert any(mat[j][1] and mat[j][2] for j in ids)==rec["hit"]
                if t=="read":assert sum(row["candidates"][i][3]+1 for i in ids)==ar["emitted_bytes"]<=2048
                for j,col in enumerate(("hit","novel_lines","bad_new")):data[m][t][j]+=rec[col]
    for m,sets in data.items():
        for t,values in sets.items():assert values==[s["arms"][m][t][x] for x in ("hit","novel_lines","bad_new")]
    a=read(D/"historical-audit.json")["stats"];assert a["exact"]+a.get("wrong",0)+a.get("unknown_rows",0)==a["rows"]==read(D/"input-seal.json")["all_receipt_rows"]
    if (D/"manifest.json").exists():assert all(sha(D/n)==dg for n,dg in read(D/"manifest.json")["files"].items())
    print("Verified all 2696 x 12 predictions, matched controls, counts and original receipt coverage.")
if __name__=="__main__":main()

"""Verify the portable final five-seed canonical readout against its preregistered files."""
import gzip,hashlib,json,math
from pathlib import Path
D=Path(__file__).resolve().parent
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=load(D/"canonical-manifest.json")
    res=load(D/"canonical-complete.json")
    for n,h in manifest.items():
        p=D/n
        if n in {"pipeline.py","verify.py","report.py","implementation.json"}:p=D/("registered-"+n)
        assert sha(p)==h,n
    names=("R35_oof_3894","R33_cost_worst","full_rgcn","wo_chunk_adjacency")
    for seed in (13,17,29,37,41):
        p=D/f"canonical-{seed}.json.gz";assert load(D/f"canonical-receipt-{seed}.json")["rows"]==sha(p)
        d=load(p);assert len(d)==2000 and len({v[0] for v in d.values()})==1207
        means=res["five"]["per_seed_means"][str(seed)]
        for i,n in enumerate(names,1):
            for j in range(6):
                avg=sum(v[i][j] for v in d.values())/len(d)
                assert abs(avg-means[n][j])<1e-11
    if (D/"manifest.json").exists():
        for k,h in load(D/"manifest.json")["files"].items():assert sha(D/k)==h
    print("Verified 5 seeds, 4 rankings and 6 metrics")
if __name__=="__main__":main()


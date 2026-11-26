import gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    obs=read(D/"outcomes.json.gz");plan=read(D/"schedule.json.gz");stats=read(D/"results.json")
    assert obs.keys()==plan.keys() and sha(D/"outcomes.json.gz")==stats["outcomes"]
    t=0
    for k,summary in stats["counts"].items():
        rows=[r for q in obs for r in obs[q][k]]
        assert all(len(obs[q][k])==len(plan[q]["sets"][k]) for q in obs)
        assert len(rows)==summary["treatments"] and sum(r[3] for r in rows)==summary["unchanged"]
        assert all(r[2]==r[3] and r[1]<=r[2] and len(bytes.fromhex(r[4]))==32 for r in rows)
        assert summary["avoidable_barrier_recompute"]==sum(not r[1] and r[3] for r in rows)
        assert summary["false_hit_selected"]==sum(r[0] and not r[3] for r in rows);t+=len(rows)
    if (D/"manifest.json").exists():
        for k,h in read(D/"manifest.json")["files"].items():assert sha(D/k)==h
    print(t,stats["synthetic"])
if __name__=="__main__":main()


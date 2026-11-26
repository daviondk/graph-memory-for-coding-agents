"""Verify the signed portable packet set and recompute its scores without native model dependencies."""
import gzip,hashlib,json
from collections import defaultdict
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    files=read(D/"manifest.json")["files"]
    for name,h in files.items():assert sha(D/name)==h,name
    fs=read(D/"forecast-seal.json");fp=read(D/"packets.json.gz");gold=read(D/"dev-judgments.json.gz")
    src=read(D/"pool.json.gz")
    assert fs["forecasts"]==sha(D/"packets.json.gz") and set(src)==set(fp)==set(gold) and len(src)==580
    assert len({x["t"] for x in src.values()})==352
    atoms=0
    for p,o,res in [("packets","outcomes","results"),("budget-packets","budget-outcomes","budget-results")]:
        packets=read(D/(p+".json.gz"));out=read(D/(o+".json.gz"));tab=read(D/(res+".json"))
        assert set(out)==set(src)==set(packets)
        means=defaultdict(list)
        for q,(t,panels) in packets.items():
            truth=gold[q];total=sum(w for w,_ in truth);assert t==src[q]["t"]==out[q][0]
            for j,rows in enumerate(panels):
                for a,ids in rows.items():
                    sel=set(ids);tokens=sum(src[q]["c"][i] for i in ids)
                    assert len(ids)==len(sel) and 0<=tokens<=2048
                    observed=sum(w for w,ws in truth if sel.intersection(ws))
                    v=[int(observed==total),observed/total,tokens]
                    assert out[q][1][j][a]==v
                    means[j,a].append(v);atoms+=1
        for (j,a),v in means.items():
            if not a.startswith("single_"):assert np.allclose(np.mean(v,0),tab[("recall","full_support")[j]]["means"][a])
    print("Verified",len(files),"files and",atoms,"packets across 580 queries in 352 trajectories.")
if __name__=="__main__":main()


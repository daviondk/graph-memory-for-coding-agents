import gzip,hashlib,json
from pathlib import Path
from collections import Counter
D=Path(__file__).resolve().parent
def read(n):
    p=D/n;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def main():
    m=read("manifest.json")["files"]
    assert all(hashlib.sha256((D/n).read_bytes()).hexdigest()==v for n,v in m.items())
    predicted={(r[0],r[1],r[2]):r for r in read("predictions.json.gz")}
    assert len(predicted)==74241
    result=read("results.json")
    for key in ("discovery","holdout"):
        c=Counter()
        for run,at,i,f,cat,off,inside,native_len in read(key+"-verified.json.gz"):
            p=predicted.pop((run,at,f["n"]))
            assert p[3]==i and p[6]==f["line_probe_hash"] and (key=="holdout")==bool(p[4])
            c[bool(p[7][2]),cat=="literal"]+=1
        z=result["tables"][key]["all"]["reject_suffix"]
        assert [c[True,True],c[True,False],c[False,True],c[False,False]]==[z[k] for k in ("accepted_correct","accepted_bad","rejected_correct","rejected_bad")]
    assert not predicted
    suffix=read("suffix-check.json")["counts"]
    assert suffix["tail_rows"]==suffix["tail_literal_shifted"]==9087
    print(len(m),"files, 74241 line decisions, 9087 shifted full-view rows verified")
if __name__=="__main__":main()

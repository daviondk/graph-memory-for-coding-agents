"""Check all 40,000 as-of native outcomes independently from thresholded source-span atoms."""
import gzip
import hashlib
import json
import math
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def check():
    qs=read(D/"outcomes.json.gz")
    atoms=read(D.parents[1]/"graph_memory_round34/interval_witness/test-atoms.json.gz")
    seal=read(D/"forecast-seal.json")
    count=0;seen=set()
    for idx in range(8):
        fp=D/f"predictions-{idx}.json.gz"
        assert hashlib.sha256(fp.read_bytes()).hexdigest()==seal["files"][fp.name]
        for r in read(fp):
            q=r["q"];assert q not in seen;seen.add(q);gold=atoms[q]
            total=sum(b-a for _,a,b,nodes in gold)
            for seed,methods in r["seeds"].items():
                for method,sel in methods.items():
                    s=set(sel);assert len(s)==len(sel)
                    hit=sum(b-a for _,a,b,nodes in gold if not s.isdisjoint(nodes))
                    fs,c=qs[q]["seeds"][seed][method]
                    assert (hit==total)==fs and math.isclose(hit/total,c,abs_tol=1e-12)
                    count+=1
    assert count==40000 and seen==qs.keys()
    return count
if __name__=="__main__":print(check())


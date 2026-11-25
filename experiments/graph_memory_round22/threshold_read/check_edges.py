"""Exactness regression for equal scores, varying token sizes and nonmonotone rank scores."""
import json
from pathlib import Path
import hashlib
from operators import np,index,suffix_bounds,read

HERE=Path(__file__).resolve().parent
METHODS=("vector","heap","one","two")
def check(p,s,c,order,budget):
    i=index(p,c);u=suffix_bounds(s);o=np.asarray(order,dtype=np.int64)
    # Python's exact lexicographic tie order is independently specified by original semantic rank.
    ranked=sorted(range(len(o)),key=lambda j:(-float(s[j]+p[o[j]]),j))
    for policy in ("prefix","skip"):
        remaining=budget;expect=[]
        for j in ranked:
            n=int(o[j])
            if c[n]<=remaining:
                expect.append(n);remaining-=int(c[n])
            elif policy=="prefix":break
        for method in METHODS:
            got,m=read(method,o,s,u,i,budget,policy)
            assert got==expect and len(set(got))==len(got),(method,policy,p,s,c,order,budget,got,expect)
            assert 0<=m["scored"]<=len(o)
def main():
    rng=np.random.default_rng(24317);cases=0
    for p,s,c,o,b in [
        ([],[],[],[],0),([0],[0],[11],[0],10),([1,1,1],[2,2,2],[20,3,3],[2,0,1],6),
        ([0,1,0],[0,-4,7],[3,5,3],[0,1,2],7),([7,-2,3],[1,1,1],[4,4,4],[2,0,1],8),
        ([0,0,0],[0,3,-2],[42,41,4],[0,1,2],5),([1,2],[1,0],[9,2],[0,1],0)]:
        check(np.array(p,dtype=float),np.array(s,dtype=float),np.array(c,dtype=int),o,b);cases+=1
    for n in range(1,36):
        for _ in range(24):
            p=rng.integers(-4,5,n).astype(float);s=rng.integers(-4,5,n).astype(float)
            c=rng.integers(1,24,n);o=rng.permutation(n);b=int(rng.integers(0,2*int(c.sum())))
            check(p,s,c,o,b);cases+=1
    result={"cases":cases,"method_policy_comparisons":cases*8,"seed":24317,
            "operators_sha":hashlib.sha256((HERE/"operators.py").read_bytes()).hexdigest()}
    (HERE/"edge-cases.json").write_text(json.dumps(result,sort_keys=True)+"\n",encoding="utf8")
    print("Exact on",cases,"constructed cases /",cases*8,"method-policy comparisons.")
if __name__=="__main__":main()


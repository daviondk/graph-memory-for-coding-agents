"""Exact sensitivity for the small number of documents with net paired changes."""
from collections import defaultdict
from itertools import product
from select_read import D,c

def main():
    res=c.read(D/"results.json");data=D/"per-query.json.gz";assert c.checksum(data)==res["values_sha"]
    rows=c.read(data)["rows"]; tests=[]
    for right in ("bm25","first_positive"):
        by=defaultdict(int)
        for r in rows.values():
            by[r["t"]]+=r["values"]["rank_novelty"][0]-r["values"][right][0]
        vals=[x for x in by.values() if x]
        assert len(vals)<=20
        observed=abs(sum(vals));n=2**len(vals)
        p=sum(abs(sum(a*b for a,b in zip(sign,vals)))>=observed for sign in product((-1,1),repeat=len(vals)))/n
        tests.append({"right":right,"cluster_nonzero":len(vals),"net_counts":sorted(vals),"exact_sign_flip_p":p})
    order=sorted(range(len(tests)),key=lambda i:tests[i]["exact_sign_flip_p"])
    last=0
    for j,i in enumerate(order):
        last=max(last,min(1,(len(tests)-j)*tests[i]["exact_sign_flip_p"]));tests[i]["holm_p"]=last
    c.save(D/"sparse-sensitivity.json",{"outcomes":c.checksum(data),"tests":tests})
    print(tests)
if __name__=="__main__":main()

"""All client orders on small histories, with the same packet consumed by different readers."""
from itertools import permutations, product
import json
from pathlib import Path
import sys

from wire import METHODS, receive, request, serve

ROOT=Path(__file__).resolve().parent


def check():
    cases=witnesses=0
    paths=range(4)
    for values in product(range(3), repeat=len(paths)):
        counts={i:v for i,v in enumerate(values) if v}
        for k in (1,2,3):
            boundary=set()
            answers=set()
            if sum(v>0 for v in values)>=k:
                cutoff=sorted(values,reverse=True)[k-1]
                boundary={i for i,v in enumerate(values) if v==cutoff}
            common=None
            for perm in permutations(paths):
                tie={i:len(paths)-p for p,i in enumerate(perm)}
                expected=sorted(((i,values[i]) for i in paths),
                                key=lambda t:(-t[1],perm.index(t[0])))[:k]
                answers.update(i for i,_ in expected)
                for method in METHODS:
                    req=request(method,-1,tie,k)
                    resp=serve(req,lambda _:counts,tie if method=="shared" else None,k)
                    assert receive(resp,-1,tie,k)==expected
                    if method=="frontier":
                        if common is None:
                            common=resp
                        assert resp==common
                    cases+=1
            assert boundary<=answers
            witnesses+=len(boundary)
    return {"decoded":cases,"witnessed_boundary_ids":witnesses,
            "orders_per_score_vector":24,"score_vectors":81}


if __name__=="__main__":
    value=check()
    target=ROOT/"check.json"
    if "--verify" in sys.argv:
        assert json.loads(target.read_bytes())==value
    else:
        target.write_text(json.dumps(value,indent=2)+"\n",encoding="utf8")
    print(value)

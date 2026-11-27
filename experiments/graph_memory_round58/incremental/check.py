"""Check the incremental bound for every small old vector and vector of positive increments."""
from collections import Counter
from itertools import product
from pathlib import Path
import json
import sys

from cache import advance, cut


def check():
    queries=passed=refills=loose=0
    for old in product(range(3),repeat=4):
        complete={i:v for i,v in enumerate(old) if v}
        for k in (1,2,3):
            for buffer in range(k,5):
                keep, upper=cut(complete,buffer)
                for updates in product(range(3),repeat=4):
                    delta=Counter({i:v for i,v in enumerate(updates) if v})
                    gold=Counter(complete)+delta
                    for u in (upper,upper+1):
                        if u==upper+1 and not upper:
                            continue
                        result=advance(keep,u,delta,k)
                        queries+=1
                        if result is None:
                            refills+=1
                            continue
                        known, bound=result
                        assert dict(cut(known,k)[0])==dict(cut(gold,k)[0])
                        assert all(n==gold[i] for i,n in known.items())
                        assert max((v for i,v in gold.items() if i not in known),default=0)<=bound
                        loose+=int(u!=upper)
                        passed+=1
    return dict(checks=queries,certified=passed,fallback=refills,loose_bound_certified=loose)


if __name__=="__main__":
    path=Path(__file__).with_name("check.json")
    value=check()
    if "--verify" in sys.argv:
        assert value==json.loads(path.read_bytes())
    else:
        path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf8")
    print(value)

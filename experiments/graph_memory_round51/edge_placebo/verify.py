"""Independent bit-mask enumeration; recompute null outcomes from archived query features."""
from study import *
from switch_control import run as conditioned
from functools import lru_cache
import argparse

@lru_cache(maxsize=32)
def masks(n):
    return ((np.arange(2**n)[:,None]>>np.arange(n))&1).astype(np.int8)

def verify(source=False):
    rec=rd(D/"records.json.gz");res=rd(D/"results.json");fixed=res["bonus"]
    assert res["records"]==sha(D/"records.json.gz") and res["model"]==sha(BASE/"model.json") and res["protocol"]==PLAN
    for panel,rows in rec.items():
        for q,r in rows.items():
            raw=np.array(r["raw"]);good=np.array(r["good"]);bit=np.array(r["bit"]);rank=r["ordered_hybrid"];n=len(bit)
            valid=masks(n);valid=valid[valid.sum(1)==bit.sum()]
            assert np.argmax(raw+fixed*bit)==r["winner"]
            winners=np.argmax(raw[None,:]+fixed*valid,axis=1)
            for k,b in (("pair",2),("triple",3),("unrestricted",n)):
                ok=np.ones(len(valid),bool)
                for j in range(0,n,b):
                    subset=rank[j:j+b]
                    ok &= valid[:,subset].sum(1)==bit[subset].sum()
                v=winners[ok];dst=r[k]
                assert int(good[v].sum())==dst["success"] and len(v)==dst["n"]
                assert dict(Counter(map(int,v)))=={int(i):c for i,c in dst["win"].items()}
        summary=summaries(list(rows.values()))
        for k,expected in summary.items():
            archived=dict(res["panels"][panel]["conditions"][k]);archived.pop("holm_three",None)
            assert expected==archived
    switch=rd(D/"switch.json")
    assert conditioned(rec)==switch["panels"] and switch["records"]==res["records"]
    if source:
        rows,stats=run()
        for panel,k in stats["panels"].items(): assert k==res["panels"][panel]
        assert stats["sources"]==res["sources"]
        print("Rebuilt all edge positions on the archived visible snippets and title catalogs.")
    print("Verified 3200 queries, all admissible masks in 3 nulls and all rate-matched conditional controls.")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",action="store_true");verify(p.parse_args().source)


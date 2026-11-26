"""Check the smooth-loss upper bound on true excess cost and audit the paired rankings."""
import json,gzip,hashlib
from collections import Counter
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
R33=HERE.parents[1]/"graph_memory_round33/budget_loss"
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def write():
    true=read(R33/"test-ranks.json.gz");cands=read(HERE/"test-ranks.json.gz");out=read(HERE/"test-outcomes.json.gz")
    panels={}
    for k in read(HERE/"select.json")["chosen"]:
        panels[k]={"identical_whole_ranking":sum(v[k]==true[q]["cost_worst_0.03"] for q,v in cands.items()),"identical_all_6_metrics":sum(v["arms"][k]==v["arms"]["R33"] for v in out.values())}
    train_path=Path("D:/CodexResearch/x20-r33-budget-loss/train.json.gz")
    assert hashlib.sha256(train_path.read_bytes()).hexdigest()==read(HERE/"models.json")["upstream"]
    rs=read(train_path);models=list(read(R33/"models.json")["models"].values())+list(read(HERE/"models.json")["models"].values())
    count=0;min_slack=float("inf");worst=0.
    for r in rs:
        x=np.asarray(r["x"]);o=np.asarray(r["o"]);c=np.asarray(r["c"]);p=np.zeros(len(c),bool);p[r["y"]]=True;n=~p;ids=np.arange(len(x))
        assert c[n].sum()>0
        for model in models:
            s=o+(x-model["center"])/model["scale"]@model["weights"]
            rank=np.argsort(-s,kind="stable");j=max(np.flatnonzero(p[rank]));cost=c[rank[:j+1]].sum()-c[p].sum()
            assert cost>=0
            sp=s[p];tau=.25;minimum=sp.min()
            L=minimum-tau*np.log(np.exp(-(sp-minimum)/tau).mean());surrogate=np.dot(c[n]/c[n].sum(),np.logaddexp(0.,s[n]-L))
            bound=surrogate/np.log1p(len(sp)**(-tau));risk=cost/c[n].sum()
            assert risk<=bound+1e-12
            min_slack=min(min_slack,bound-risk);worst=max(worst,bound-risk);count+=1
    vals={"pairs":panels,"train_positive_counts":dict(Counter(len(r["y"]) for r in rs)),"train_bound_checks":count,"min_bound_minus_realized":min_slack,"max_bound_minus_realized":worst}
    (HERE/"audit.json").write_bytes((json.dumps(vals,sort_keys=True,separators=(",",":"))+"\n").encode())
if __name__=="__main__":write()

"""Partial identification with a shared unknown verdict for each identical prompt."""
from collections import Counter

def bounds(rows, verdicts, first, second):
    x={r['id']:r['key'] for r in rows if r['arm']==first}
    y={r['id']:r['key'] for r in rows if r['arm']==second}
    assert set(x)==set(y)
    fixed=0;unknown=Counter();complete=[];tied_missing=0
    for t in sorted(x):
        va,vb=verdicts[x[t]],verdicts[y[t]]
        if va is not None and vb is not None:complete.append(int(va)-int(vb))
        if va is None:unknown[x[t]]+=1
        else:fixed+=int(va)
        if vb is None:unknown[y[t]]-=1
        else:fixed-=int(vb)
        tied_missing+=int(x[t]==y[t] and va is None)
    n=len(x)
    return {'n':n,'complete_pairs':len(complete),'complete_pair_delta':sum(complete)/len(complete) if complete else None,
            'shared_unknown_ties':tied_missing,'identified_delta_interval':[(fixed+sum(min(0,v) for v in unknown.values()))/n,(fixed+sum(max(0,v) for v in unknown.values()))/n]}

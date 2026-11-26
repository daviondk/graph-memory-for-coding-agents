"""Descriptive development-only ceiling over prespecified constant prior multipliers."""
import gzip,json
from pathlib import Path
from collections import Counter
D=Path(__file__).resolve().parent
def analyse():
    vals=json.loads(gzip.decompress((D/"dev-outcomes.json.gz").read_bytes()))
    arms=sorted((k for k in vals if k.startswith("alpha_")),key=lambda k:float(k[6:]))
    selected=json.loads((D/"dev-selection.json").read_bytes())["selected"]["constant"]
    hist=Counter();tot=all_success=disjoint=islands=protect=rescue=0
    for q,record in vals[selected].items():
        fs=[int(vals[a][q][1]) for a in arms];hist[sum(fs)]+=1
        best=max(fs);tot+=best;all_success+=min(fs)
        groups=sum(v and (i==0 or not fs[i-1]) for i,v in enumerate(fs));disjoint+=int(groups>1);islands+=groups
        rescue+=int(best and not record[1]);protect+=int(record[1] and not min(fs))
    return {"n":len(vals[selected]),"weights":[float(a[6:]) for a in arms],"selected_on_dev":selected,
            "oracle_hits":tot,"always_win":all_success,"always_miss":len(vals[selected])-tot,
            "flat_fs_all_weights":all_success+len(vals[selected])-tot,"rescued_by_oracle":rescue,
            "currently_supported_but_sensitive":protect,"disjoint_success_runs":disjoint,
            "hits_at_n_gridpoints":dict(sorted(hist.items())),"interpretation":"Dev-only oracle uses labels to choose an action per query; upper bound over the registered finite grid only. Disconnected grid runs do not characterize untested intermediate values."}
if __name__=="__main__":
    print(json.dumps(analyse(),ensure_ascii=False,sort_keys=True,indent=2))
"""Independent reconstruction of the primary end-to-end scores from observed strings."""
from pathlib import Path
from collections import defaultdict
from statistics import mean
import numpy as np
from tokenizers import Tokenizer
from handoff import D,P,PRIOR,get,sha,save,h,TOKEN

def main():
    tok=Tokenizer.from_file(str(TOKEN));tok.no_truncation()
    raw={c["cp"]:c["events"] for c in get(P/"prefix.json.gz")}
    meta={r["group"]:r for r in get(PRIOR/"delivery-metadata.json.gz") if r["view"]=="repo_only"}
    gold=get(D/"targets.json.gz");rc=get(D/"results.json")
    assert sha(D/"outcomes.json.gz")==rc["outcomes"];rows=get(D/"outcomes.json.gz");N=0
    for r in rows:
        cp=r["cp"];t=gold[meta[r["group"]]["q"]];events=sorted([e for e in raw[cp] if e["lines"]],key=lambda e:(len(e["lines"]),e["idx"]),reverse=True)
        left=512;widest={};seen=set()
        for e in events:
            path=e["path"];lines=e["lines"]
            if path in seen:continue
            seen.add(path);addr=f'{path}@{e["idx"]}[{lines[0][0]}-{lines[-1][0]}]'
            n=len(tok.encode(addr,add_special_tokens=False).ids)
            if n<=left:widest[path]=e;left-=n
        e=widest.get(t["path"])
        for policy in ("forward","boundary"):
            keys=set();spent=0
            if e:
                lines=e["lines"];lo=0;hi=len(lines)-1;turn=0
                while lo<=hi:
                    if policy=="forward" or turn%2==0:i=lo;lo+=1
                    else:i=hi;hi-=1
                    turn+=1;num,text=lines[i];ln=f'[{e["path"]}:{num}] {text}'
                    n=len(tok.encode(ln,add_special_tokens=False).ids)
                    if spent+n<=512:keys.add((num,h(text)));spent+=n
            expected=[]
            for positions in ("ends","inner"):
                indicators=[tuple(k) in keys for k in t[positions]]
                expected.extend([int(all(indicators)),mean(indicators)])
            expected.extend([int(e is not None),512-left,spent,512-left+spent])
            assert r["arms"]["one_wide/"+policy]==expected,(r["group"],policy);N+=1
    pool=[r for r in rows if r['scope']=='main_takeovers' and r['split']=='test'];by=defaultdict(list)
    for r in pool:by[r['issue']].append(r)
    diff=[mean(r['arms']['one_wide/boundary'][0]-r['arms']['one_wide/forward'][0] for r in by[i]) for i in sorted(by)]
    vals=np.asarray(diff);rng=np.random.default_rng(32031)
    limits=np.quantile([rng.choice(vals,size=len(vals)).mean() for _ in range(10000)],[.025,.975])
    metric=rc['groups']['main_takeovers/test']['contrasts']['one_wide/boundary vs one_wide/forward']['boundary_pair']
    assert np.allclose(limits,metric['interval'],atol=1e-12,rtol=0) and abs(mean(diff)-metric['diff'])<1e-12
    save(D/'audit.json',dict(primary_arms_rebuilt=N,test_rows=len(pool),test_issues=len(by),bootstrap=list(limits),source=sha(P/'prefix.json.gz'),results=sha(D/'results.json'),code=sha(Path(__file__))))
if __name__=="__main__":main()
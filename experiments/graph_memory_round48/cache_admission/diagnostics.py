"""Descriptive scan timing and earlier-history depth after the registered analysis."""
from pathlib import Path
from collections import defaultdict,Counter
import json,gzip
D=Path(__file__).resolve().parent
def get(k):
    b=(D/k).read_bytes();return json.loads(gzip.decompress(b) if k.endswith('.gz') else b)
def main():
    w=get('workload.json.gz');pre=w['pre'];out=get('outcomes.json.gz');gd=get('gdsf-outcomes.json.gz');r=w['rows'];g=get('results.json')['budgets'];ans={}
    for q,z in r.items():
        ns={}
        for c,v in g.items():
            ev=pre[q];cap=v['slots'];lru=[];saved=0
            for u in ev+[q]:
                for k in r[u]['order']:
                    hit=k in lru
                    if hit:lru.remove(k)
                    lru.append(k);lru=lru[-cap:]
                    if u==q and hit:saved+=r[u]['docs'][str(k)]
            ns[c]=saved
        ans[q]=ns
    depth={}
    for bucket,owner in [('cold',lambda n:n==0),('one',lambda n:n==1),('two_plus',lambda n:n>=2)]:
        qs=[q for q,v in pre.items() if owner(len(v))]
        a=lambda q,k:out[q]['caps']['512'][k]['saved'];data={'states':len(qs),'tokens':sum(r[q]['tokens'] for q in qs)}
        for arm in ['proposed','cost','hot_lru','tiny']:
            data[arm]=sum(a(q,arm) for q in qs)
        for m in ['source','batch']:data[m]=sum(gd[q]['512'][m]['saved'] for q in qs)
        depth[bucket]=data
    v=dict(totals_streaming={c:sum(s[c] for s in ans.values()) for c in g},streaming_unique_by_state=ans,depth=depth)
    (D/'diagnostic.json').write_text(json.dumps(v,sort_keys=True,separators=(',',':'))+'\n',encoding='utf8')
    print(depth)
if __name__=='__main__':main()


"""Check the complete CPU-only study using only the Python standard library and this directory."""
from pathlib import Path
from statistics import mean
import sys
from verify_panel import HERE,verify,v
def run():
    manifest=v.get(HERE/'MANIFEST_SHA256.json');assert all(v.sha(HERE/f)==h for f,h in manifest.items())
    for method in ('availability','hash64'):
        sub=HERE/method;child=v.get(sub/'MANIFEST_SHA256.json');assert all(v.sha(sub/f)==h for f,h in child.items())
        verify(method)
    sub=HERE/'hash64';ss=v.get(sub/'topology-seal.json');assert v.sha(sub/'topology-forecasts.json.gz')==ss['pred']
    g={q:v.merged(a) for q,a in v.get(HERE/'inputs/test-gold.json.gz').items()}
    baseline={r['q']:r for f in sub.glob('forecasts-rgcn-*.json.gz') for r in v.get(f)}
    results={(r['q'],r['arm']):r for r in v.get(sub/'topology-outcomes.json.gz')};count=0
    for r in v.get(sub/'topology-forecasts.json.gz'):
        q=r['q'];pool={a['node_id']:a for a in baseline[q]['rr']}
        for name,order in r['orders'].items():
            assert len(order)==len(pool) and set(pool)==set(order)
            chosen=v.pack(order,pool,{},'prefix')
            assert chosen==r['chosen'][name];v.check(v.metric(g[q],[pool[x] for x in chosen]),results[q,name]);count+=1
    assert count==6000
    print(len(manifest),'hashes, all 30000 main and 6000 topology measurements verified')
if __name__=='__main__':run()


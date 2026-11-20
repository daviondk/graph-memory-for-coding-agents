"""Offline archive audit using Python stdlib; no dataset, model or GPU dependency."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
D=Path(__file__).resolve().parent

def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(n):
    b=(D/n).read_bytes()
    return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)

def main():
    manifest=D/'MANIFEST_SHA256.json'
    if manifest.exists():
        for n,s in load(manifest.name).items():assert h(D/n)==s,n
    for n,s in load('forecast.lock.json').items():assert h(D/n)==s,n
    seal=load('evaluation.lock.json')
    assert seal['forecasts']==h(D/'forecast.lock.json')
    for n,s in seal['files'].items():assert h(D/n)==s,n
    pred=load('predictions.json.gz'); snapshots=load('tie_order.json.gz')
    outcomes=load('evaluation_rows.json.gz'); res=load('results.json')
    pairs=load('paired.json');inference=load('inference.json')
    stat={}
    for panel,L in pred.items():
        lookup={r['id']:r for r in L}
        links=0;empty=0
        for r in L:
            ranks=r['ranks'];scores=r['scores']
            tie={p:i for i,p in enumerate(snapshots[panel][r['id']])}
            paths=set(tie)
            for m,rk in ranks.items():assert len(rk)==len(paths) and set(rk)==paths
            for m,sc in scores.items():
                assert set(sc)==paths
                assert sorted(paths,key=lambda p:(-sc[p],tie[p]))==ranks[m]
            for typ in ('strong','graph','shuffled','uniform'):
                a={p:i for i,p in enumerate(ranks['dense'],1)};b={p:i for i,p in enumerate(ranks[typ],1)}
                merged=sorted(paths,key=lambda p:(-(1/(60+a[p])+1/(60+b[p])),tie[p]))
                assert merged==ranks['rrf_'+typ]
            links+=len(paths);empty+=int(not paths)
        for ep,rs in outcomes[panel].items():
            ref=res[panel][ep]
            assert len(rs)==ref['n'] and len({r['iid'] for r in rs})==ref['tasks']
            assert len({r['id'] for r in rs})==len(rs)
            assert sum(r['reachable'] for r in rs)==ref['reachable']
            tally=defaultdict(lambda:[0,0,0.])
            for r in rs:
                match=lookup[r['id']]; goal=set(r['targets'])
                assert set(match['ranks']['dense']).isdisjoint(goal)==(not r['reachable'])
                for m,names in match['ranks'].items():
                    pos=next((j for j,p in enumerate(names,1) if p in goal),0)
                    assert pos==r['ranks'][m]
                    tally[m][0]+=pos==1;tally[m][1]+=0<pos<=3;tally[m][2]+=1/pos if pos else 0
            for m,(s1,s3,mrr) in tally.items():
                t=ref['methods'][m]
                assert (s1,s3)==(t['h1'],t['h3']) and abs(mrr/len(rs)-t['mrr'])<1e-12
            for name,cs in pairs[panel][ep].items():
                a,b=name.split('__minus__')
                for m,row in cs.items():
                    u=ref['methods'][a][m]-ref['methods'][b][m]
                    assert abs((u if m=='mrr' else u/len(rs))-row['delta'])<1e-12
                    assert row['wins']+row['losses']+row['ties']==len(rs)
        counts=inference['counts'][panel]
        assert (len(L),links,empty)==(counts['anchors'],counts['pairs'],counts['empty'])
        stat[panel]={'forecast_count':len(L),'pair_count':links,'empty':empty}
    assert sum(v['forecast_count'] for v in stat.values())==340
    print(json.dumps(stat))
if __name__=='__main__':main()

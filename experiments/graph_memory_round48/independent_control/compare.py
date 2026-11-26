"""Only after forecast sealing, compare full ordered outputs and registered singleton decisions."""
from check import D,read,write,digest
from collections import Counter
import argparse
def compare():
    pins=read(D/'forecast-seal.json')
    assert all(digest(D/n)==h for n,h in pins.items())
    forecast=read(D/'results.json.gz')
    groups=read(D.parent/'support_updates/group-packets.json.gz')
    pairs=read(D.parent/'support_updates/packets.json.gz')
    counts=Counter()
    for label,rows in [('example',[forecast['example']]),('controls',forecast['controls'])]:
        for row in rows:
            q=row['q'];step=row['step'];changes=row['changes'];bit={c[0]:1<<i for i,c in enumerate(changes)}
            for cap,ab in row['cases'].items():
                masks={m:p['ids'] for m,p in ab['packets']}
                g=next(v for v in groups[q] if v['step']==step and v['cap']==int(cap))
                assert masks[0]==g['base'] and masks[(1<<len(changes))-1]==g['after']
                counts['group_packets_compared_'+label]+=2
                srt=sorted(ident for ident,m in bit.items() if masks[m]==masks[0])
                assert srt==g['single_same'];counts['single_same_compared_'+label]+=len(bit)
                for v in pairs[q]['events']:
                    if v['step']!=step or v['cap']!=int(cap):continue
                    a=bit[v['a']];b=bit[v['b']]
                    for m,n in [(0,'before'),(a,'first'),(b,'second'),(a|b,'after')]:
                        if m in masks:
                            assert masks[m]==v[n];counts['pair_packets_compared_'+label]+=1
    e=forecast['example'];c=e['cases']['4'];p0=c['packets'][0][1]['ids']
    for mask,p in c['packets']:
        assert (p['ids']!=p0)==((mask&36)==36)
    return {'comparisons':dict(counts),'example_change_requires_producers':[5,18],
            'source_projection_sha256':read(D/'input-seal.json')['projection_sha256'],'forecast_seal_sha256':digest(D/'forecast-seal.json')}
if __name__=='__main__':
    c=argparse.ArgumentParser();c.add_argument('--write',action='store_true');a=c.parse_args();o=compare()
    if a.write:write(D/'comparison.json',o)
    assert read(D/'comparison.json')==o
    print(o['comparisons'])

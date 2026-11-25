"""Standalone verification of all released scores and paired point effects."""
from pathlib import Path
from statistics import mean
import gzip
import hashlib
import json
import math

HERE=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=read(HERE/'diversity-plan.json')
    assert p['code']==sha(HERE/'diversify.py') and p['method']==sha(HERE/'DIVERSITY_RU.md')
    for result in sorted(HERE.glob('diversity-*-score.json')):
        tag=result.name[len('diversity-'):-len('-score.json')]
        pre=HERE/f'diversity-{tag}'
        def file(name):return HERE/(pre.name+'-'+name)
        yield_=read(result)
        assert yield_['seal']==sha(file('seal.json'))
        assert read(file('seal.json'))['pred']==sha(file('selections.json.gz'))
        assert yield_['outcomes']==sha(file('outcomes.json.gz'))
        selection=read(file('selections.json.gz'));rows=read(file('outcomes.json.gz'))
        assert len(selection)==len(rows)==2000 and len({r['q'] for r in rows})==2000
        for r,s in zip(rows,selection,strict=True):
            assert r['q']==s['q'] and r['t']==s['t']
            for arm,measures in r['measures'].items():
                assert 0<=measures['tokens']<=2048 and len(set(s['selections'][arm]))==len(s['selections'][arm])
                assert measures['events']<=len(s['selections'][arm])
                assert (measures['event']==1)==bool(measures['full_support'])
                if r['m']==2:
                    assert measures['pair']==measures['full_support']
        for bucket,part in yield_['panels'].items():
            sub=[r for r in rows if bucket=='all' or r['m']>=2]
            assert len(sub)==part['n'] and len({r['t'] for r in sub})==part['tr']
            for arm,stats in part['methods'].items():
                for k,value in stats.items():
                    assert math.isclose(mean(r['measures'][arm][k] for r in sub),value,abs_tol=1e-13)
            for key,ds in part['contrasts'].items():
                left,right=key.split(' minus ')
                for k,v in ds.items():
                    assert math.isclose(part['methods'][left][k]-part['methods'][right][k],v['difference'],abs_tol=1e-13)
        print(tag,2000,'selection and score rows verified')
if __name__=='__main__':
    main()

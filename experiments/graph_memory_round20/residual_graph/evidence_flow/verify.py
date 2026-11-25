"""Independent point estimates from released counts; only Python's standard library is required."""
from pathlib import Path
from statistics import mean
import gzip
import hashlib
import json
import math

HERE=Path(__file__).resolve().parent
def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix=='.gz' else b)

def h(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def eq(x,y):
    assert math.isclose(x,y,abs_tol=1e-13,rel_tol=1e-13),(x,y)

def main():
    man=read(HERE/'MANIFEST_SHA256.json')
    assert set(man)=={p.name for p in HERE.iterdir() if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    for name,dig in man.items():
        assert h(HERE/name)==dig
    for path in sorted(HERE.glob('*-results.json')):
        label=path.name[:-len('-results.json')]
        result=read(path)
        rp=HERE/f'{label}-events.json.gz'
        assert result['records']==h(rp)
        rows=read(rp)
        assert len({r['q'] for r in rows})==len(rows)==516
        for scope,res in result['partitions'].items():
            group=[r for r in rows if scope=='minimum_two' or r['m']==2]
            assert len(group)==res['n'] and len({r['t'] for r in group})==res['trajectories']
            for arm,values in res['arms'].items():
                p=mean(r['k'][arm]/r['m'] for r in group)
                j=mean(r['k'][arm]*(r['k'][arm]-1)/(r['m']*(r['m']-1)) for r in group)
                all_=mean(r['k'][arm]==r['m'] for r in group)
                for k,x in dict(event=p,pair=j,all=all_,marginal_square=p*p,covariance=j-p*p,partner_given_first=j/p).items():
                    eq(x,values[k])
                if scope=='exactly_two':
                    eq(j,all_)
            for pair,delta in res['contrasts'].items():
                a,b=pair.split(' minus ')
                for m,v in delta.items():
                    eq(res['arms'][a][m]-res['arms'][b][m],v['difference'])
                    assert v['ci95'][0]<=v['ci95'][1]
                eq(delta['pair']['difference'],delta['covariance']['difference']+delta['marginal_square']['difference'])
        print(label,len(rows),'point estimates and nonlinear decomposition verified')

if __name__=='__main__':
    main()

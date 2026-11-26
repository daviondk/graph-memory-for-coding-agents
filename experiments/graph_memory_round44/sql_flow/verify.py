"""Independently verify witness weights, complete maps, final physical records and elapsed-time sums."""
import hashlib
import json
import sqlite3
from collections import Counter
from common44 import D,load,sha

def main():
    m=D/'manifest.json'
    if m.exists():
        files=load(m)['files']
        assert files=={p.name:sha(p) for p in D.iterdir() if p.is_file() and p!=m}
    design=load(D/'design-seal.json')
    assert all(sha(D/p)==h for p,h in design.items())
    assert load(D/'registration.json')['protocol']==sha(D/'PROTOCOL_RU.md')
    sealed=load(D/'fixture-seal.json');assert sealed['fixture']==sha(D/'normalized.json.gz')
    assert sealed['code']==sha(D/'fixture.py') and sealed['registration']==sha(D/'registration.json')
    assert sealed['times']==sha(D/'extraction-times.json.gz')
    rows=load(D/'normalized.json.gz');pairs=[];vertices=[];checks=Counter();fingerprint=hashlib.sha256()
    for t,tr in enumerate(rows):
        weights=Counter()
        for delta,ref in tr:
            fingerprint.update((json.dumps([t,sorted(delta),ref],separators=(',',':'))+'\n').encode())
            for a,b,w in delta:
                weights[a,b]+=w
                assert w in (-1,1) and weights[a,b]>=0
                if w>0:checks['adds']+=1
                else:checks['retracts']+=1
                if weights[a,b]==0:del weights[a,b]
            sums={}
            for (a,b),w in weights.items():
                sums.setdefault(a,[0,0])[0]+=w;sums.setdefault(b,[0,0])[1]+=w
            assert ref==[[v,int(o>0)+2*int(i>0)] for v,(o,i) in sorted(sums.items())]
            checks['boundaries']+=1;checks['live_bits']+=sum(f.bit_count() for v,f in ref);checks['nonempty']+=bool(delta)
        pairs.extend((t,a,b,w) for (a,b),w in sorted(weights.items()))
        vertices.extend((t,v,o,i) for v,(o,i) in sorted(sums.items()))
    checks['traces']=len(rows)
    for name in ('pair','ends','co'):
        db=sqlite3.connect((D/(name+'.sqlite')).as_uri()+'?mode=ro&immutable=1',uri=True)
        if name in ('pair','co'):assert list(db.execute('SELECT t,a,b,w FROM pair ORDER BY t,a,b'))==pairs
        if name in ('ends','co'):assert list(db.execute('SELECT t,v,nout,nin FROM endpoint ORDER BY t,v'))==vertices
        assert db.execute('PRAGMA quick_check').fetchone()==('ok',);db.close()
    result=load(D/'results.json');run=load(D/'run-seal.json')
    assert result['counts']==checks and result['run']==sha(D/'run-seal.json')
    assert run['fixture']==sealed['fixture'] and run['code']==sha(D/'operators.py') and run['runner']==sha(D/'replay.py')
    for f,h in run['records'].items():
        assert sha(D/f)==h
        v=load(D/f)
        for a,values in v['clocks'].items():
            w,r,val,cold,warm=map(sum,zip(*values));assert len(values)==1207
            assert result['timing_ns_per_repetition'][f"{v['reads']}/{v['rep']}/{a}"]==[w,r,w+r,val,cold,warm]
            if a in ('pair','ends','co'):assert (D/(a+'.sqlite')).stat().st_size==v['info'][a]['file_bytes']
    assert all(a['objects']==b['objects'] for a,b in zip(result['physical']['pair'],result['physical']['scan']))
    print(dict(checks),'final pairs',len(pairs),'final vertices',len(vertices),'canonical groups',fingerprint.hexdigest())

if __name__=='__main__':main()

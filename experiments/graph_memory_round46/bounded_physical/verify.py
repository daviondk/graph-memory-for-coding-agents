"""Rebuild independent exact endpoints, check the authoritative and auxiliary database contents, and verify timing statistics."""
import sqlite3,json
from collections import Counter
from math import isqrt
from analyze import D,read,sha,analyze
from cycle_stats import calculate
from compact_stats import calculate as check_compact
def main():
    manifest=read(D/'manifest.json')['files'];assert all(sha(D/n)==h for n,h in manifest.items())
    i=D/'inputs';reg=read(D/'registration.json')
    assert reg['reference']==sha(i/'r44-operators.py') and reg['fixture']==sha(i/'normalized.json.gz') and reg['parent_checks']==sha(i/'r45-checks.json')
    assert reg['protocol']==sha(D/'PROTOCOL_RU.md') and reg['runner']==sha(D/'run.py') and reg['operators']==sha(D/'operators.py')
    old=read(i/'r45-checks.json');assert old['records_sha256']==sha(i/'r45-per-trace.json.gz')
    raw=read(i/'normalized.json.gz');lower=read(i/'r45-per-trace.json.gz')
    pairs=[];directions=[];exists_calls=[];boundaries=0
    for t,frames in enumerate(raw):
        weights=Counter();nc=0
        for batch,expected in frames:
            changes=Counter()
            for a,b,s in batch:weights[a,b]+=s;assert weights[a,b]>=0;changes[a,0]+=s;changes[b,1]+=s
            sums={}
            for (a,b),v in weights.items():
                if v==0:continue
                sums.setdefault(a,[0,0])[0]+=v;sums.setdefault(b,[0,0])[1]+=v
            assert expected==[[v,int(x>0)+2*int(y>0)] for v,(x,y) in sorted(sums.items())]
            nc+=sum(n<0 for n in changes.values());boundaries+=1
        exists_calls.append(nc)
        pairs.extend((t,a,b,n) for (a,b),n in sorted(weights.items()) if n)
        directions.extend((t,v,x,y) for v,(x,y) in sorted(sums.items()))
    for arm in ('scan','distinct','exact','packed','eager','deferred','exists'):
        uri=(D/(arm+'.sqlite')).as_uri()+'?mode=ro&immutable=1'
        db=sqlite3.connect(uri,uri=True);assert db.execute('pragma quick_check').fetchall()==[('ok',)]
        assert db.execute('select t,a,b,w from pair order by t,a,b').fetchall()==pairs
        if arm=='exact':assert db.execute('select * from endpoint order by t,v').fetchall()==directions
        if arm in ('packed','eager','deferred','exists'):
            rows=db.execute('select t,v,s from aux order by t,v').fetchall();assert len(rows)==len(directions)
            for (t,v,s),(k,h,x,y) in zip(rows,directions):
                assert (t,v)==(k,h) and s&3==int(x>0)+(2*int(y>0))
                if arm=='packed':assert s>>2==(x+y)*(x+y+1)//2+y
                if arm=='exists':assert s<=3
                if arm in ('deferred','eager'):
                    for actual,enc in zip((x,y),divmod(s>>2,7)):
                        assert actual==enc if enc<=3 else enc-3<=actual
        db.close()
    r=read(D/'results.json');assert r==analyze() and r['boundaries']==boundaries and r['traces']==len(raw)
    assert calculate()==read(D/'cycle-results.json') and check_compact()==read(D/'compact-results.json')
    for f in D.glob('run-*.json.gz'):
        a=read(f);observed=a['records']
        assert [x[4] for x in observed['exists']]==exists_calls
        for arm,k in [('eager','3-0'),('deferred','3-1'),('deferred_memo','3-1')]:assert [x[4] for x in observed[arm]]==[x['arms'][k][0] for x in lower]
        for arm,st in a['storage'].items():
            source=D/(arm.removesuffix('_memo')+'.sqlite');assert st['file']==source.stat().st_size
            assert sum(o[2] for o in st['objects'])==st['file']
    print('Verified',boundaries,'boundaries,',len(pairs),'final authoritative edges, all seven database files, six main passes and six locality passes.')
if __name__=='__main__':main()


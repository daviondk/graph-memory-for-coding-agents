"""Probe source-weight selection from the separately started, isolated demo with a brute-force check of interval validity."""
from urllib.parse import urlencode
import json

def probe(base,get):
    def response(route,**query):
        return json.loads(get(base+'/api/weights/'+route+'?'+urlencode(query)))
    assert b'/api/weights/' in get(base+'/weights')
    catalog=response('catalog')
    assert sorted(catalog['queries'])==[f'q{i:02d}' for i in range(1,41)]
    assert (catalog['low'],catalog['high'])==(-(1<<30),1<<30)
    checks=0
    witness_count=0
    for q in catalog['queries']:
        sources=response('sources',q=q)['sources']
        witness_count+=len(sources)
        s=sources[0]['id']
        baseline=response('packet',q=q,s=s,delta=0)
        rows=baseline['intervals']; assert 'verification' not in baseline
        assert rows[0]['lo']==catalog['low'] and rows[-1]['hi']==catalog['high']
        assert all(left['hi']+1==right['lo'] and left['id']!=right['id'] for left,right in zip(rows,rows[1:]))
        for d in sorted({0,*(v[key] for v in rows for key in ('lo','hi'))}):
            out=response('verify',q=q,s=s,delta=d)
            selected=out['after']['members']
            assert out['verification']['members']==selected
            assert out['verification']['tokens']==out['after']['tokens']<=2048
            assert out['lo']<=d<=out['hi'] and out['unchanged']==(out['before']['members']==selected)
            assert [v['id'] for v in rows if v['lo']<=d<=v['hi']]==[out['after']['id']]
            checks+=1
    assert witness_count==2528 and checks>300
    return {'source_choices':witness_count,'live_boundary_checks':checks,'queries':len(catalog['queries'])}

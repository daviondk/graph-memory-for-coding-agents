"""Exercise joint-source views in the running sealed demo using an independently fixed 40-query selection."""
from collections import defaultdict
import json
from urllib.parse import urlencode

def probe(base,get):
    def call(route,**params):
        return json.loads(get(base+'/api/joint/'+route+'?'+urlencode(params)))
    assert b'/api/joint/' in get(base+'/joint')
    catalog=call('catalog');by_query=defaultdict(list)
    for ident,query in catalog['pairs']:by_query[query].append(ident)
    assert len(by_query)==40 and len(catalog['pairs'])==1862
    witness=call('state',**catalog['example'])
    assert 'audit' not in witness
    packets=witness['packets']
    assert packets['base']['members']==packets['first']['members']==packets['second']['members']
    assert packets['joint']['members']!=packets['base']['members']
    probe_count=0
    for query,ids in by_query.items():
        for x,y in [(-(1<<30),1<<30),(1<<28,1<<28)]:
            known=call('audit',pair=ids[0],x=x,y=y)
            assert known['query']==query and known['audit']['equal']
            returned=known['packets']['joint']
            assert known['audit']['members']==returned['members'] and returned['tokens']<=2048
            candidates=known['planes']
            top=max(a*x+b*y+c for a,b,c,k in candidates)
            first=next(k for a,b,c,k in candidates if a*x+b*y+c==top)
            assert first==returned['id']
            probe_count+=1
    assert call('audit',**catalog['example'])['audit']['equal']
    return dict(pairs=len(catalog['pairs']),queries=len(by_query),independent_rank_checks=probe_count,
        witness_base=packets['base']['id'],witness_joint=packets['joint']['id'],witness_axes_unchanged=True)

"""Cross-check the observed transaction shown by the running demo against the independent exact-weight solver."""
import gzip,json
from pathlib import Path
from itertools import combinations
from urllib.parse import urlencode
D=Path(__file__).resolve().parent
def probe(base,get):
    def req(route,**params):
        return json.loads(get(base+'/api/observed/'+route+'?'+urlencode(params)))
    assert b'/api/observed/' in get(base+'/observed')
    c=req('catalog');all_groups=c['groups'];assert len(all_groups)==54 and c['example']==['q25',9]
    truth=json.loads(gzip.decompress((D/'independent_control/results.json.gz').read_bytes()))['example']
    assert [truth['q'],truth['step']]==c['example']
    ids=[v[0] for v in truth['changes']]
    accepted_masks={0,63,*[1<<j for j in range(6)],*[1<<a|1<<b for a,b in combinations(range(6),2)]}
    checks=0
    for cap in (1,4):
        sampled={m:v for m,v in truth['cases'][str(cap)]['packets'] if m in accepted_masks}
        for m,pack in sampled.items():
            selected=[n for j,n in enumerate(ids) if m&(1<<j)]
            out=req('check',q='q25',step=9,cap=cap,set=','.join(map(str,selected)))
            assert out['checked'] and out['members']==out['after']==pack['ids'] and out['new_tokens']==pack['tokens'];checks+=1
    assert checks==46
    for q,step in all_groups:
        bare=req('show',q=q,step=step,cap=1,set='all')
        assert 'checked' not in bare and bare['new_tokens']<=2048
        full=req('check',q=q,step=step,cap=4,set='all')
        assert full['checked'] and full['after']==full['members']
    return dict(groups=len(all_groups),independent_subset_checks=checks,changed_only_when_both=[5,18])

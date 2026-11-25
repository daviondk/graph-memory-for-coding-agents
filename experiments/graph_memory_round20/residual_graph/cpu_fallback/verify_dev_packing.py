"""Independent exact check of all three dev policy lists using the original dev call IDs."""
from verify_panel import v,HERE,ROOT
from pathlib import Path
import gzip,json,sys
TR=ROOT.parents[1]/'graph_memory_round19/trained_rank'
DATA=Path('D:/CodexResearch/x20-isetrace-trained/projection/dev')
def put(p,d):
    p.write_bytes((json.dumps(d,sort_keys=True,indent=2)+'\n').encode())
def source():
    raw={};split=v.get(TR/'split.json.gz')['dev'];ts=sorted({r['t'] for r in split})
    for t in ts:
        rec=v.get(DATA/f'{t}.json.gz');assert rec['t']==t
        M={n['item_id']:[n['metadata'].get('call_id'),n['metadata'].get('node_kind')] for n in rec['pool']};assert len(M)==len(rec['pool']);raw[t]=M
    dest=HERE/'dev-call-map.json.gz';dest.write_bytes(gzip.compress((json.dumps(raw,sort_keys=True,separators=(',',':'))+'\n').encode(),compresslevel=4,mtime=0))
    put(HERE/'dev-call-map-receipt.json',dict(sha=v.sha(dest),trajectories=len(ts),split_sha=v.sha(TR/'split.json.gz'),n=sum(map(len,raw.values()))))
def verify(name):
    sub=HERE/name;maps=v.get(HERE/'dev-call-map.json.gz');assert v.sha(HERE/'dev-call-map.json.gz')==v.get(HERE/'dev-call-map-receipt.json')['sha']
    counts=0;lock=v.get(sub/'forecast-seal.json')
    for method in ('rgcn','seed'):
        p=sub/f'dev500-pu-{method}-ranks.json.gz';assert v.sha(p)==lock['files'][p.name]
        for r in v.get(p):
            pool={n['node_id']:n for n in r['rr']};order=[n['node_id'] for n in r['rr']];assert set(pool)==set(maps[r['t']])
            for arm,ids in r['arms'].items():assert v.pack(order,pool,maps[r['t']],arm)==ids;counts+=1
    assert counts==3000
    put(HERE/f'dev-packing-check-{name}.json',dict(complete=counts,seed_and_rgcn=True,source_native_call_attributes=True,forecast_seal=v.sha(sub/'forecast-seal.json')))
if __name__=='__main__':
    if sys.argv[1]=='source':source()
    else:verify(sys.argv[1])


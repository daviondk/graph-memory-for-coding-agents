"""Recalculate primary and secondary effects and verify every arm without hardware."""
import hashlib,math,json,gzip
from collections import Counter
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def read(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    seal=read(D/'seal.json');scores=read(D/'results.json');runs=read(D/'receipts.json.gz')
    oracle=read(D/'oracle.json.gz');quality=read(D/'quality.json.gz');heap=read(D/'heap.json')
    assert seal['receipts']==sha(D/'receipts.json.gz') and seal['signature']['runner']==sha(D/'runner.py') and seal['signature']['protocol']==sha(D/'PROTOCOL_RU.md') and scores['source']==sha(D/'seal.json')
    assert set(scores['repos'])==runs.keys() and len(runs)==8 and len(oracle)==24
    assert sum(v for k,v in seal['warmup'].items() if 'cuda' in k.lower())>0
    assert Counter(seal['order'])==Counter(['PFV','VFP','FVP','PVF','VPF','FPV','PFV','FVP'])
    for i in range(3):assert sorted(Counter(order[i] for order in seal['order']).values())==[2,3,3]
    count=0
    for repo,rr in runs.items():
        refseq=[z['q'] for z in rr['proposed']]
        for arm,trace in rr.items():
            previous=set()
            assert [z['q'] for z in trace]==refseq and len(trace)==3
            for j,z in enumerate(trace):
                assert set(z['resident_in'])==previous
                costs=dict(zip(z['doc_keys'],z['doc_tokens']))
                hit=costs.keys() & previous
                assert z['hit']==len(hit) and z['tokens']==z['query_tokens']+sum(n for k,n in costs.items() if k not in hit)
                assert set(z['resident_out'])<=previous|costs.keys() and len(z['resident_out'])<=31
                expected_bytes=256+len(z['resident_out'])*(16384+64)+(1024 if arm=='proposed' else 40*z['ghost_keys'])
                assert z['persistent_bytes']==expected_bytes and expected_bytes<=524288
                assert heap['sizes'][repo][arm][j]<=heap['max_bytes'][arm]
                previous=set(z['resident_out']);q=z['q'];ref=oracle[q];qc=quality[q][arm]
                assert ref['ids']==z['ids'] and qc['vector_matches']==sum(x==y for x,y in zip(ref['vector_sha'],z['vector_sha']))
                rank=np.argsort(-np.asarray(z['scores']),kind='stable').tolist();assert rank==z['rank']
                assert qc['rank_equal']==(ref['rank']==rank) and np.isclose(qc['max_score_error'],max(abs(x-y) for x,y in zip(ref['scores'],z['scores'])))
                for k in [5,8]:
                    select=set(rank[:k]);gold=ref['labels'];ok=[len(set(s)&select)>=m for m,w,s in gold['groups']]
                    assert qc['mss'+str(k)]==float(all(ok) or any(set(s)<=select for s in gold['alternatives']))
                    assert np.isclose(qc['group'+str(k)],sum(ok)/len(ok) if ok else 1.)
                assert math.isclose(z['compute_engine_s'],sum(v for k,v in z['device_engines'].items() if any(s in k.lower() for s in ('cuda','3d','compute')))) and z['compute_engine_s']>0
                assert z['wall_commit']>=z['wall_rank']>=z['rpc_wall']>0
                count+=1
            for k,s in scores['groups'][repo][arm].items():assert np.isclose(s,sum(z[k] for z in trace))
    names=scores['repos'];bs=np.random.default_rng(492321).multinomial(8,np.full(8,.125),size=20000);cc=0
    for arm,cmp in scores['comparisons'].items():
        for k,v in cmp.items():
            x=np.array([sum(z[k] for z in runs[n]['proposed']) for n in names]);y=np.array([sum(z[k] for z in runs[n][arm]) for n in names])
            assert np.isclose(1-x.sum()/y.sum(),v['advantage']) and np.allclose(np.percentile(1-(bs@x)/(bs@y),[2.5,97.5]),v['ci']);cc+=1
    if (D/'manifest.json').is_file():
        for k,val in read(D/'manifest.json')['files'].items():assert sha(D/k)==val
    print('Verified',count,'matched hardware records,',cc,'paired repository intervals, exact ranks, underlying requests and budgets.')


if __name__=='__main__':main()


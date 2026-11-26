"""Standalone numerical verification of the campaign and the primary cluster contrasts."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,gzip,math
import numpy as np
D=Path(__file__).resolve().parent
def g(f):
    b=(D/f).read_bytes();return json.loads(gzip.decompress(b) if f.endswith('.gz') else b)
def h(f):return hashlib.sha256((D/f).read_bytes()).hexdigest()
def main():
    raw=g('raw-runs.json.gz');r=g('results.json');jud=g('ordinal-judgments.json.gz');qc=g('quality.json.gz');s=g('run-seal.json');pan=g('panel.json');repo=[x['repo'] for x in pan['selected']]
    assert len(set(repo))==len(repo)==8 and s['raw']==h('raw-runs.json.gz') and r['seal']==h('run-seal.json') and s['sig']['runner']==h('run_gpu.py') and s['sig']['pdh']==h('pdh.py') and s['sig']['protocol']==h('PROTOCOL_RU.md')
    expected=[]
    for z in sorted(pan['all'],key=lambda v:v['priority']):
        if z['repo'] not in [x['repo'] for x in expected]:expected.append(z)
        if len(expected)==8:break
    assert [z['seq'] for z in expected]==[z['seq'] for z in pan['selected']]
    positions=defaultdict(Counter);neighbors=Counter();n=0
    for c in pan['selected']:
        rep=c['repo'];seq=c['seq'];m=c['methods'];assert len(seq)>=3 and len(set(m))==4
        for j,a in enumerate(m):positions[a][j]+=1
        neighbors.update(zip(m,m[1:]))
        for x,y in zip(seq,seq[1:]):
            first=pan['scope'][x]['events'];last=pan['scope'][y]['events'];assert first==last[:len(first)] and len(first)<len(last)
        for a in m:
            old=set();sums=Counter()
            for j,z in enumerate(raw[rep][a]):
                q=seq[j];assert q==z['q'] and sorted(old)==z['resident_in'];now=dict(zip(z['doc_keys'],z['doc_tokens']));miss=now.keys()-old
                if a=='fresh':tokens=z['query_tokens']+sum(z['doc_tokens']);assert not old and not z['resident_out']
                else:tokens=z['query_tokens']+sum(now[k] for k in miss);assert z['hit']==len(old&now.keys()) and set(z['resident_out'])<=old|now.keys()
                assert tokens==z['tokens'] and len(z['resident_out'])<=31 and z['persistent_bytes']<=524288
                assert z['wall_commit']>=z['wall_rank']>=z['rpc_wall']>0 and z['tokenizer_wall']>0 and z['compute_engine_s']>0
                assert np.isclose(z['compute_engine_s'],sum(v for k,v in z['device_engines'].items() if any(w in k.lower() for w in ('3d','compute','cuda'))))
                old=set(z['resident_out']);ref=raw[rep]['fresh'][j];rr=np.argsort(-np.array(z['scores']),kind='stable').tolist();assert rr==z['rank'];v=qc[rep][a][q]
                assert v['vector_exact']==sum(x==y for x,y in zip(z['vector_sha'],ref['vector_sha'])) and v['full']==(rr==ref['rank']) and np.isclose(v['max_score_error'],max(abs(x-y) for x,y in zip(z['scores'],ref['scores'])))
                for idx,k in enumerate((5,8)):
                    ab=set(rr[:k]);d=jud[q];ok=[len(ab&set(ss))>=quota for quota,wt,ss in d['groups']]
                    assert v['mss'][idx]==float(all(ok) or any(set(t)<=ab for t in d['alternatives'])) and np.isclose(v['group'][idx],sum(ok)/len(ok) if ok else 1.)
                for key in r['chain_totals'][rep][a]:sums[key]+=z[key]
                n+=1
            for k,val in sums.items():assert math.isclose(val,r['chain_totals'][rep][a][k])
    assert all(list(c.values())==[2]*4 for c in positions.values()) and len(neighbors)==12 and all(v==2 for v in neighbors.values())
    bs=np.random.default_rng(490731).multinomial(8,np.repeat(1/8,8),size=20000)
    for arm in ['lru','gdsf','fresh']:
        t=r['contrasts']['proposed vs '+arm]
        for k,v in t.items():
            xx=np.array([r['chain_totals'][z]['proposed'][k] for z in repo]);yy=np.array([r['chain_totals'][z][arm][k] for z in repo]);ratio=1-xx.sum()/yy.sum();ci=np.percentile(1-(bs@xx)/(bs@yy),[2.5,97.5])
            assert np.allclose(ci,v['ci']) and np.isclose(ratio,v['saving'])
    if (D/'manifest.json').is_file():assert all(h(k)==v for k,v in g('manifest.json')['files'].items())
    print('Independently verified',n,'measured full rankings, balanced treatment order, 21 paired intervals, physical hits, official outcomes, vector hashes and GPU counters.')
if __name__=='__main__':main()


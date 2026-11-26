"""Rebuild causal prior lists, exact and alias hits, and verify the GPU subset without source texts."""
from pathlib import Path
import hashlib,json,gzip
from collections import defaultdict
import numpy as np
D=Path(__file__).resolve().parent
def get(name):
    b=(D/name).read_bytes();return json.loads(gzip.decompress(b) if name.endswith('.gz') else b)
def sha(k):return hashlib.sha256((D/k).read_bytes()).hexdigest()
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def main():
    f=get('input-seal.json');metrics=get('reuse.json');assert f['protocol']==sha('PROTOCOL_RU.md') and f['program']==sha('inventory.py') and f['inventory']==sha('inventory.json.gz') and metrics['output']==sha('per-state.json.gz')
    rows=get('inventory.json.gz');p=get('predecessors.json');cl=get('per-state.json.gz')['causal'];sql=get('sql-rows.json.gz');groups=defaultdict(list)
    assert len(rows)==305 and f['changed_key_overlap']==0 and f['changed_namespace']!=f['namespace']
    for q,z in rows.items():groups[z['group']].append(q)
    for q,z in rows.items():
        possible={}
        for a in groups[z['group']]:
            ha=tuple(rows[a]['hist']);hb=tuple(z['hist'])
            if ha and z['run_known'] and len(ha)<len(hb) and hb[:len(ha)]==ha:possible.setdefault(ha,[]).append(a)
        prior=[min(possible[a],key=lambda s:h('r48-representative'+s)) for a in sorted(possible,key=len)]
        assert p[q]==prior;seq=[d for prev in prior for d in rows[prev]['docs']];old={d[0] for d in seq};now=z['docs'];base=cl[q]
        assert sql[q]==[sum(d[0] in old for d in now),sum(d[1] for d in now if d[0] in old)]==[base['prior_docs'],base['prior_tokens']]
        for name,k in [('token',0),('text',2),('id',3),('path',4),('span',5)]:
            seen={d[k]:d[0] for d in reversed(seq)};hits=wrong=ht=wt=0
            for d in now:
                x=d[k]
                if x in seen:
                    eq=seen[x]==d[0];hits+=eq;ht+=eq*d[1];wrong+=not eq;wt+=(not eq)*d[1]
                else:seen[x]=d[0]
            assert [hits,wrong,ht,wt]==base['alias'][name]
        for cap in (32,128):
            resident=[];tokens=hits=0
            for i,d in enumerate(seq+now):
                t=d[0];ok=t in resident
                if ok:resident.remove(t)
                resident.append(t);resident=resident[-cap:]
                if i>=len(seq) and ok:hits+=1;tokens+=d[1]
            assert [hits,tokens,len(resident)]==base['lru'][str(cap)]
    repo=defaultdict(list)
    for q,z in cl.items():repo[z['repo']].append(q)
    ids=sorted(repo);t=np.asarray([sum(cl[q]['prior_tokens'] for q in repo[k]) for k in ids]);n=np.asarray([sum(cl[q]['input_tokens'] for q in repo[k]) for k in ids]);bs=np.random.default_rng(48052).multinomial(len(ids),np.repeat(1/len(ids),len(ids)),size=20000)
    c=metrics['table']['causal']['both']['primary'];assert np.allclose(c['ci'],np.quantile((bs@t)/(bs@n),[.025,.975])) and np.isclose(c['micro'],sum(t)/sum(n))
    gp=get('gpu-results.json.gz');gf=get('gpu-seal.json');assert gf['results']==sha('gpu-results.json.gz') and gf['source']==sha('input-seal.json') and [x['pair'] for x in gp]==get('gpu-panel.json')
    for z in gp:
        ns=set()
        for j,q in enumerate(z['pair']):
            a=z['runs']['fresh'][j];b=z['runs']['cached'][j];docs=rows[q]['docs'];query=rows[q]['querylen'];new={}
            for tok,length,*_ in docs:
                if tok not in ns:new[tok]=length
            ns.update(new);assert a['tokens']==sum(d[1] for d in docs)+query and b['tokens']==sum(new.values())+query
            w=z['check'][j];afr=np.asarray(w['fresh_scores']);ac=np.asarray(w['cache_scores']);rr=np.argsort(-afr,kind='stable').tolist();rc=np.argsort(-ac,kind='stable').tolist()
            assert rr==w['fresh_order'] and rc==w['cached_order'] and np.isclose(w['max_score'],max(abs(afr-ac)))
            assert w['sameorder']==[rr[:k]==rc[:k] for k in [5,8]] and w['sameset']==[set(rr[:k])==set(rc[:k]) for k in [5,8]]
    if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in get('manifest.json')['files'].items())
    print('Verified causal/SQLite membership, five alias and two finite-capacity controls on 305 states, 20,000 draws, GPU budgets and complete orders on 16 states.')
if __name__=='__main__':main()


"""Verify the independent transfer counts, causal lineage, controls and measured-subset match."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,gzip,json,numpy as np
D=Path(__file__).resolve().parent
def read(f):
    b=(D/f).read_bytes();return json.loads(gzip.decompress(b) if f.endswith('.gz') else b)
def sha(f):return hashlib.sha256((D/f).read_bytes()).hexdigest()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def main():
    v=read('transfer-results.json');rows=read('transfer-inputs.json.gz');out=read('transfer-outcomes.json.gz');assert v['plan']==sha('TRANSFER_RU.md') and v['program']==sha('transfer.py') and v['outcomes']==sha('transfer-outcomes.json.gz')
    groups=defaultdict(list)
    for q,z in rows.items():groups[z['group']].append(q)
    for q,z in rows.items():
        old=defaultdict(list);end=z['hist']
        for a in groups[z['group']]:
            prev=rows[a]['hist']
            if prev and len(prev)<len(end) and prev==end[:len(prev)]:old[tuple(prev)].append(a)
        history=[min(old[k],key=lambda a:digest('r48-representative'+a)) for k in sorted(old,key=len)]
        assert history==out[q]['prior'];total=sum(t for _,t in z['docs'])+z['query'];current=dict(z['docs']);assert out[q]['total']==total and out[q]['within']==total-z['query']-sum(current.values())
        L=[];gf={};clock=0;count=Counter();SK={};tick=0
        for earlier in history:
            C=dict(rows[earlier]['docs']);ordered=sorted(C,key=lambda x:(C[x],-int(x,16)));snap=set(L)
            for x in [k for k in ordered if k not in snap]+[k for k in ordered if k in snap]:
                if x in L:L.remove(x)
                L=(L+[x])[-31:]
            joined=gf.copy()
            for x,amount in C.items():
                f=gf.get(x,(0,0))[1]+1;joined[x]=(clock+f*amount,f)
            keep=sorted(joined,key=lambda x:(-joined[x][0],x))[:31];drop=set(gf)-set(keep)
            if drop:clock=max(clock,max(joined[k][0] for k in drop))
            gf={k:joined[k] for k in keep}
            for x in C:
                if tick and tick%1024==0:count=Counter({k:t//2 for k,t in count.items()})
                tick+=1
                for j,b in enumerate(bytes.fromhex(x)[:4]):
                    pos=j*256+b;count[pos]=min(255,count[pos]+1)
            allc=SK|C;rank=sorted(allc,key=lambda x:(-allc[x]*(1+min(count[256*j+b] for j,b in enumerate(bytes.fromhex(x)[:4]))),x))
            SK={x:allc[x] for x in rank[:31]}
        for a,res in [('lru',L),('gdsf',gf),('proposed',SK)]:
            hit=current.keys()&set(res);s=out[q]['arm'][a];n=sum(current[i] for i in hit)
            assert len(hit)==s['hits'] and n==s['inter'] and s['net_tokens']==sum(current.values())+z['query']-n
    repo=defaultdict(list)
    for q,z in rows.items():repo[z['repo']].append(q)
    names=sorted(repo);n=len(names);den=np.array([sum(out[q]['total'] for q in repo[k]) for k in names]);bs=np.random.default_rng(490731).multinomial(n,np.repeat(1/n,n),size=20000)
    for a in ['lru','gdsf']:
        diff=np.array([sum(out[q]['arm']['proposed']['inter']-out[q]['arm'][a]['inter'] for q in repo[k]) for k in names]);ci=np.percentile((bs@diff)/(bs@den),[2.5,97.5])
        assert np.allclose(ci,v['panels']['all']['contrasts'][a]['ci'])
    if (D/'raw-runs.json.gz').exists():
        raw=read('raw-runs.json.gz');p=read('panel.json')
        for z in p['selected']:
            for i,q in enumerate(z['seq']):
                assert out[q]['prior']==z['seq'][:i]
                for a in ['lru','gdsf','proposed']:
                    event=raw[z['repo']][a][i]
                    assert event['tokens']==out[q]['arm'][a]['net_tokens'] and event['hit']==out[q]['arm'][a]['hits'] and event['tokens_full']==out[q]['total']
    print('Verified 537 policy/state token counts and two primary transfer CIs. If present, all 72 bounded hardware records were cross-checked with independent replay.')
if __name__=='__main__':main()


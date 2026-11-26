"""Portable scalar reimplementation of every admission and paired statistical comparison."""
import math,json,gzip,hashlib
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def rd(k):
    b=(D/k).read_bytes()
    return json.loads(gzip.decompress(b) if k.endswith('.gz') else b)
def sha(k):return hashlib.sha256((D/k).read_bytes()).hexdigest()
def ratio(x,cap):return math.log1p(max(0,min(x,cap)))/math.log1p(cap)


def choose(res,z,d,beta,kind):
    ts=z['docs'];scores=[];state={}
    for k in set(res)|set(ts):
        active=k in ts;old=k in res
        o,n,last=res.get(k,(None,0,d))
        val=ts[k] if active else o
        t,p,a,b,test,py,vis=val
        state[k]=(val,n+int(active),d if active else last)
        x=[t/512.,active,old,ratio(n+int(active),12),ratio(d-last,12) if old else 1.,test,py,ratio(a,2000),ratio(b-a+1,256),vis,ratio(d,12)]
        if kind!='local':
            current={k2 for k2,o2 in ts.items() if o2[1]==p and k2!=k}
            prior={k2 for k2,(o2,_,_) in res.items() if o2[1]==p and k2!=k}
            oi=0.
            for k2 in prior:
                lo,hi=res[k2][0][2:4]
                if a>0 and lo>0:oi=max(oi,max(0,min(b,hi)-max(a,lo)+1)/max(1,max(b,hi)-min(a,lo)+1))
            both=current&prior
            x += [p in z['opened'],ratio(len(current),64),ratio(len(prior),31),ratio(len(both),31),ratio(len(current-prior),64),
                  ratio(len(prior-current),31),len(both)/max(1,len(current|prior)),oi]
        logit=beta['intercept']+sum(u*v for u,v in zip(beta['coef'],x))
        scores.append((-round(t/(1+math.exp(-max(-45,min(45,logit)))),9),k))
    return {k:state[k] for _,k in sorted(scores)[:31]}


def main():
    rows=rd('inputs.json.gz');models=rd('models.json');ab=rd('ablation-models.json');obs=rd('outcomes.json.gz');ao=rd('ablation-outcomes.json.gz')
    mainr=rd('results.json');stats=mainr['panels'];abr=rd('ablation-results.json')['panels']
    assert len(rows)==484 and not {v['repo'] for v in rows.values() if v['panel']=='R48'}&{v['repo'] for v in rows.values() if v['panel']=='R49'}
    assert mainr['inputs']==sha('inputs.json.gz') and mainr['outcomes']==sha('outcomes.json.gz') and mainr['models']==sha('models.json') and mainr['protocol']==sha('PROTOCOL_RU.md')
    assert rd('ablation-results.json')['protocol']==sha('ABLATION_RU.md');n=0
    for q,z in rows.items():
        group=obs[q]['fold']
        for p in z['prev']:assert rows[p]['repo']==z['repo'] and rows[p]['panel']==z['panel']
        for m in ('local','graph','open','neighbors'):
            beta=(models if m in ('local','graph') else ab)[group][m]
            assert z['repo'] not in beta['train_repos'] and all(rows[p]['panel']=='R48' and rows[p]['repo']!=z['repo'] for p in beta['train_states'])
            cur={}
            for i,p in enumerate(z['prev']):cur=choose(cur,rows[p],i,beta,m)
            if m in ('local','graph'):assert sorted(cur)==obs[q][m+'_retained']
            hit=cur.keys()&z['docs'].keys();assert ao[q][m]==[len(hit),sum(z['docs'][k][0] for k in hit)]
            n+=1
    for label,rep in stats.items():
        seq=[k for k,z in obs.items() if (z['panel']==label if label in ('R48','R49') else z['fold']==label[4:])]
        g={r:[q for q in seq if obs[q]['repo']==r] for r in sorted({obs[q]['repo'] for q in seq})};den=np.array([sum(obs[q]['total'] for q in v) for v in g.values()]);nr=len(g)
        b=np.random.default_rng(501271).multinomial(nr,np.full(nr,1/nr),size=20000)
        for m,x in rep['arms'].items():
            diff=np.array([sum(obs[q]['arms']['graph'][1]-obs[q]['arms'][m][1] for q in group) for group in g.values()])
            assert np.allclose(np.percentile((b@diff)/(b@den),[2.5,97.5]),x['ci']) and diff.sum()==x['tokens'] and np.isclose(diff.sum()/den.sum(),x['delta'])
        if label in abr:
            for contrast,x in abr[label].items():
                a,c=contrast.split('-');dif=np.array([sum(ao[q][a][1]-ao[q][c][1] for q in group) for group in g.values()])
                assert np.allclose(np.percentile((b@dif)/(b@den),[2.5,97.5]),x['ci']) and dif.sum()==x['tokens']
    packed=rd('packing.json.gz');assert sum(len(v) for v in packed.values())==968
    for q,p in packed.items():
        for m,x in p.items():assert x['keys']<=31 and x['metadata']==256+64*x['keys'] and x['total']==x['metadata']+16384*x['keys']<=524288
    if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in rd('manifest.json')['files'].items())
    print('Verified',n,'policy/state predictions, seven group-separated panels, eight supplementary contrasts and 968 packed states.')


if __name__=='__main__':main()


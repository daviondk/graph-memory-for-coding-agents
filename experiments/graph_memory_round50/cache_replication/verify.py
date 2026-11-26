"""Standalone reconstruction of predictions, observed token costs, and metadata bridge counts."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,json,hashlib,math
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


def controls(history, data, name):
    freq=Counter();tick=0;res={};clock=0
    for p in history:
        z=data[p];cost={k:z['docs'][k][0] for k in z['order']}
        if name=='cost_hot_lru':
            old=set(res)
            for k in sorted(cost,key=lambda k:(k in old,cost[k],-int(k,16))):
                res.pop(k,None);res[k]=cost[k]
                if len(res)>31:del res[next(iter(res))]
        elif name=='gdsf':
            joined=dict(res)
            for k,n in cost.items():
                f=res.get(k,(0,0))[1]+1;joined[k]=(clock+n*f,f)
            keep=sorted(joined,key=lambda k:(-joined[k][0],k))[:31];dropped=set(res)-set(keep)
            if dropped:clock=max(clock,max(joined[k][0] for k in dropped))
            res={k:joined[k] for k in keep}
        else:
            if name=='frequency_cost':
                for k in cost:
                    if tick and tick%1024==0:freq=Counter({i:c//2 for i,c in freq.items()})
                    tick+=1
                    for j,b in enumerate(bytes.fromhex(k)[:4]):
                        ix=256*j+b;freq[ix]=min(255,freq[ix]+1)
            merged=res|cost
            def score(k):
                prior=1+min(freq[256*j+b] for j,b in enumerate(bytes.fromhex(k)[:4])) if name=='frequency_cost' else 1
                return (-merged[k]*prior,k)
            res={k:merged[k] for k in sorted(merged,key=score)[:31]}
    return set(res)


def main():
    inputs=rd('inputs.json.gz');out=rd('outcomes.json.gz');r=rd('results.json');scope=rd('test-panel.json.gz');s=rd('selection.json');bridge=rd('bridge.json')
    assert r['source']==sha('inputs.json.gz') and r['forecasts']==sha('outcomes.json.gz') and s['test_panel']==sha('test-panel.json.gz')
    assert len(inputs)==len(out)==len(scope)==491 and sum(bool(z['prev']) for z in inputs.values())==252 and not any(s['overlap'].values())
    assert not s['gate'] and bridge['gate'] and sha('PROTOCOL_RU.md')==s['protocol'] and sha('ORIGINAL_IDS_RU.md')==bridge['plan']
    for f,expected in [('cal-lineage.json.gz',(218,203,193)),('bridge-cal.json.gz',(184,184,184))]:
        z=rd(f);v=[r for r in z.values() if r['pred']]
        assert (len(v),sum(a['pred'][-1:]==a['true'][-1:] for a in v),sum(a['pred']==a['true'] for a in v))==expected
    model=rd('frozen-models.json');count=0
    for q,z in inputs.items():
        assert z['prev']==scope[q]['prior']
        for p in z['prev']:assert scope[p]['scope']==scope[q]['scope'] and scope[p]['step']<scope[q]['step']
        for m,fore in out[q]['arms'].items():
            if m in model:
                cur={}
                for j,p in enumerate(z['prev']):cur=choose(cur,inputs[p],j,model[m],m)
                kept=set(cur)
            else:kept=controls(z['prev'],inputs,m)
            assert sorted(kept)==out[q]['residents'][m] and len(kept)<=31
            hits=kept&z['docs'].keys();assert [len(hits),sum(z['docs'][k][0] for k in hits)]==fore
            count+=1
    groups=defaultdict(list)
    for q,z in inputs.items():groups[z['repo']].append(q)
    ids=[groups[k] for k in sorted(groups)]
    n=len(ids);bs=np.random.default_rng(501271).multinomial(n,np.full(n,1/n),size=20000)
    den=np.array([sum(inputs[k]['total'] for k in g) for g in ids])
    for m,s in r['stats'].items():
        diff=np.array([sum(out[k]['arms']['graph'][1]-out[k]['arms'][m][1] for k in g) for g in ids])
        assert np.isclose(s['delta'],diff.sum()/den.sum()) and np.isclose(s['macro_delta'],np.mean(diff/den)) and s['diff']==int(sum(diff)) and np.allclose(s['ci'],np.percentile((bs@diff)/(bs@den),[2.5,97.5]))
    if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in rd('manifest.json')['files'].items())
    print('Verified',count,'policy-by-state predictions, 252 inferred transitions, two lineage validations and paired intervals on 43 repositories.')


if __name__=='__main__':main()


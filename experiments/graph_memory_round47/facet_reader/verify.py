"""Independent numerical audit from packaged forecasts/probabilities; no text, models or gold backend needed."""
from pathlib import Path
from collections import defaultdict
from itertools import accumulate
import gzip,json,hashlib,math
import numpy as np
D=Path(__file__).resolve().parent
def get(k):
    b=(D/k).read_bytes();return json.loads(gzip.decompress(b) if k.endswith('.gz') else b)
def sha(k):return hashlib.sha256((D/k).read_bytes()).hexdigest()
def main():
    s=get('seal.json');r=get('results.json');fp=get('predictions.json.gz');pr=get('predicted-roles.json.gz');gold=get('ordinal-judgments.json.gz');out=get('outcomes.json.gz');pan=get('panels.json')
    assert sha('PROTOCOL_RU.md')==s['protocol'] and sha('fit_predict.py')==s['code'] and sha('features.py')==get('feature-seal.json')['program']
    assert sha('predictions.json.gz')==s['pred'] and sha('predicted-roles.json.gz')==s['numbers'] and sha('model.json')==s['model'] and sha('seal.json')==r['seal']
    assert len(fp)==len(pr)==len(gold)==315 and len(set(pan['train'])&set(fp))==0
    checks=0;orders=0
    for q,v in fp.items():
        y=gold[q];a=v['rank'];n=len(v['ids']);truth=[(set(e),k,w) for k,w,e in y['groups']];alts=list(map(set,y['alts']))
        raw=pr[q];z=np.asarray(raw['p']);g=(z/np.max(z,axis=0))*raw['demand'];g/=np.max(np.sum(g,axis=1));rand=g.copy()
        for i in range(n):
            h=hashlib.sha256(f'R47-placebo/{q}/{i}'.encode()).digest();rand[i]=g[i][sorted(range(4),key=lambda j:(h[j],j))]
        for base in ['bm','qwen']:
            if base not in a:continue
            initial=a[base];pri=np.zeros(n);pri[initial]=1/np.sqrt(1+np.arange(n));lx=np.zeros(n);lx[a['bm']]=1/np.sqrt(1+np.arange(n));un=np.asarray(raw['union']);un/=un.max()
            for mask in ['', '_mask']:
                allowed=[i for i in initial if not mask or not v['seen'][i]];tail=[i for i in initial if i not in allowed]
                for name in ['dynamic','static','placebo','lex','union']:
                    vec=rand if name=='placebo' else g;f=pri+.65*(un if name=='union' else lx if name=='lex' else vec.sum(1))
                    if name in ['static','lex','union']:expected=sorted(allowed,key=lambda i:-f[i])
                    else:
                        expected=[];res=np.ones(4);active=np.zeros(n,dtype=bool);active[allowed]=True
                        for j in range(len(allowed)):
                            values=pri+(.65*vec*res).sum(1);values[~active]=-np.inf
                            i=initial[int(np.argmax(values[initial]))];expected.append(i);active[i]=False;res=res*(1-vec[i])
                    assert expected+tail==a[base+'_'+name+mask],(q,base,name,mask)
                    orders+=1
        for name,seq in a.items():
            assert sorted(seq)==list(range(n))
            cum=list(accumulate(y['cost'][i] for i in seq));cap=[sum(x<=budget for x in cum) for budget in (2048,6144)]
            ks=[5,8,*[min(8,k) for k in cap],*cap];stats=out[q]['arms'][name];assert stats['items']==ks and stats['tokens']==[cum[k-1] if k else 0 for k in ks]
            ms=[];rec=[];we=[]
            for k in ks:
                ids=set(seq[:k]);h=[len(opts&ids)>=k0 for opts,k0,_ in truth];w=[ww for _,_,ww in truth]
                ms.append(float(all(h) or any(x<=ids for x in alts)));rec.append(sum(h)/len(h) if h else 1.);we.append(sum(vv*pp for vv,pp in zip(w,h))/sum(w) if sum(w) else float(not h))
            assert np.allclose(stats['metric'],ms[:4]+rec[:2]+we[:1]+ms[4:],rtol=0,atol=1e-12)
            checks+=1
    for part in ['dev','test','outside','pilot']:
        qs=pan[part];ss=r['panels'][part]
        for m,obs in ss['arms'].items():
            total=[sum(out[q]['arms'][m]['metric'][k] for q in qs) for k in range(9)]
            assert np.allclose(total,obs['total'])
    qs=pan['outside'];tab=defaultdict(list)
    for q in qs:tab[fp[q]['repo']].append(q)
    repos=sorted(tab);n=len(repos);counts=np.asarray([len(tab[k]) for k in repos]);bs=np.random.default_rng(4721401).multinomial(n,np.repeat(1/n,n),size=20000)
    for a,b,k in [('qwen_dynamic','qwen_static',0),('qwen_union_mask','qwen_mask',1),('qwen_union','qwen',8)]:
        sums=np.asarray([sum(out[q]['arms'][a]['metric'][k]-out[q]['arms'][b]['metric'][k] for q in tab[repo]) for repo in repos])
        draws=[np.dot(row,sums)/np.dot(row,counts) for row in bs]
        actual=np.percentile(draws,[2.5,97.5]);ref=r['panels']['outside']['contrasts'][a+' minus '+b]
        assert np.allclose(actual,[z[k] for z in ref['ci']]) and math.isclose(ref['micro'][k],sum(sums)/sum(counts))
    if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in get('manifest.json')['files'].items())
    assert checks*2==r['checks']
    print('Verified',orders,'complete learned/control rankings, all',checks,'outcome rows, 9 metrics, 6 cost scenarios, independent primary & both highlighted secondary CIs.')
if __name__=='__main__':main()


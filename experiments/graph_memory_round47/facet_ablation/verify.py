"""Check read-side equations, ordinal certificates, costs, and predeclared cluster interval without artifacts from sibling studies."""
from pathlib import Path
from collections import defaultdict
from itertools import accumulate
import gzip,json,hashlib,math
import numpy as np
D=Path(__file__).resolve().parent
def get(name):
    b=(D/name).read_bytes();return json.loads(gzip.decompress(b) if name.endswith('.gz') else b)
def sha(name):return hashlib.sha256((D/name).read_bytes()).hexdigest()
def main():
    s=get('learning-seal.json');f=get('forecast-seal.json');v=get('results.json');r=get('predictions.json.gz');p=get('probabilities.json.gz');o=get('outcomes.json.gz');j=get('ordinal-judgments.json.gz')
    assert s['protocol']==sha('PROTOCOL_RU.md') and s['model']==sha('models.json') and s['prob']==sha('probabilities.json.gz') and s['code']==sha('train_model.py')
    assert f['source']==sha('learning-seal.json') and f['rows']==sha('predictions.json.gz') and f['code']==sha('experiment.py') and v['forecast']==sha('forecast-seal.json')
    assert v['outcomes']==sha('outcomes.json.gz') and v['gold']==sha('ordinal-judgments.json.gz') and set(p)==set(r)==set(o)==set(j)
    count=0
    for q,z in r.items():
        a=z['rank'];src=a['qwen'];n=len(src);prior=np.zeros(n);prior[src]=1/np.sqrt(1+np.arange(n));seen=z['seen'];tail=[i for i in src if seen[i]]
        for m in ['full','document','match']:
            proba=np.asarray(p[q][m]);scores=prior+.65*proba/proba.max();expect=sorted(src,key=lambda i:-scores[i]);assert a[m]==expect and a[m+'_mask']==[i for i in expect if not seen[i]]+tail
        assert a['qwen_mask']==[i for i in src if not seen[i]]+tail
        for name,idx in a.items():
            assert list(range(n))==sorted(idx);costs=list(accumulate(j[q]['cost'][k] for k in idx));cap=[sum(c<=b for c in costs) for b in (2048,6144)];ns=[5,8,*[min(8,c) for c in cap],*cap];got=o[q]['arms'][name]
            assert got['items']==ns and got['tokens']==[costs[n0-1] if n0 else 0 for n0 in ns]
            ms=[];gr=[];wg=[]
            for k in ns:
                aset=set(idx[:k]);groups=j[q]['groups'];flags=[len(aset&set(opt))>=quota for quota,w,opt in groups];weights=[t[1] for t in groups]
                ms.append(float(all(flags) or any(set(alt)<=aset for alt in j[q]['alts'])));gr.append(sum(flags)/len(flags) if flags else 1.);wg.append(sum(ok*w for ok,w in zip(flags,weights))/sum(weights) if sum(weights) else float(not flags))
            assert np.allclose(ms[:4]+gr[:2]+wg[:1]+ms[4:],got['metric']);count+=1
    pan=get('panels.json')
    for label,summary in v['panels'].items():
        qs=pan[label];assert summary['states']==len(qs)
        for m,body in summary['arms'].items():
            assert np.allclose([sum(o[q]['arms'][m]['metric'][k] for q in qs) for k in range(9)],body['totals'])
    qs=pan['dev'];blocks=defaultdict(list)
    for q in qs:blocks[o[q]['repo']].append(q)
    repos=sorted(blocks);n=len(repos);assert n==34
    counts=np.asarray([len(blocks[k]) for k in repos]);diff=np.asarray([sum(o[q]['arms']['full_mask']['metric'][1]-o[q]['arms']['document_mask']['metric'][1] for q in blocks[k]) for k in repos])
    b=np.random.default_rng(471018).multinomial(n,np.repeat(1/n,n),size=20000)
    ci=np.percentile([np.dot(w,diff)/np.dot(w,counts) for w in b],[2.5,97.5]);target=v['panels']['dev']['contrasts']['full_mask minus document_mask'];assert np.allclose(ci,[x[1] for x in target['ci']])
    if (D/'manifest.json').exists():assert all(sha(k)==h for k,h in get('manifest.json')['files'].items())
    print('Independently checked',count,'rankings x nine outcomes, six cost regimes, four panel statistics and the primary interval.')
if __name__=='__main__':main()


"""Reconstruct every ranking and certificate, costs and cluster intervals using only packaged numerical inputs."""
from pathlib import Path
from collections import defaultdict
from itertools import accumulate
import hashlib,gzip,json,math
import numpy as np
D=Path(__file__).resolve().parent
def get(name):
    b=(D/name).read_bytes();return json.loads(gzip.decompress(b) if name.endswith('.gz') else b)
def sha(k):return hashlib.sha256((D/k).read_bytes()).hexdigest()
def main():
    seal=get('forecast-seal.json');r=get('results.json');pred=get('predictions.json.gz');raw=get('qwen-scores.json.gz');gold=get('ordinal-judgments.json.gz');out=get('outcomes.json.gz');s=r['summary']
    assert sha('PROTOCOL_RU.md')==seal['sig']['protocol'] and sha('predict_gpu.py')==seal['sig']['program'] and sha('qwen-scores.json.gz')==seal['raw'] and sha('predictions.json.gz')==seal['pred']
    assert sha('forecast-seal.json')==r['forecast'] and sha('outcomes.json.gz')==r['outcomes'] and sha('ordinal-judgments.json.gz')==r['ordinals'] and get('anchor.json')['rank_match']
    assert set(pred)==set(raw)==set(out)==set(gold)==set(seal['order']) and len(pred)==101
    blocks=defaultdict(list);comps=0
    for q in seal['order']:
        z=pred[q];n=len(z['ids']);inverted={i:k for k,i in enumerate(z['ids'])};scores=raw[q]['scores'];order=[inverted[k] for k in sorted(scores,key=lambda k:(-scores[k],k))]
        norm=max(z['p']);v={k:1/math.sqrt(j+1)+.65*z['p'][k]/norm for j,k in enumerate(order)};uni=sorted(order,key=lambda j:-v[j]);tail=[j for j in order if z['seen'][j]]
        candidate=dict(qwen=order,union=uni,qwen_mask=[j for j in order if not z['seen'][j]]+tail,union_mask=[j for j in uni if not z['seen'][j]]+tail)
        assert candidate==z['rank'];row=gold[q]
        for m,series in candidate.items():
            costs=list(accumulate(row['cost'][j] for j in series));c=[sum(t<=k for t in costs) for k in (2048,6144)];ns=[5,8,min(8,c[0]),min(8,c[1]),*c]
            arr=out[q]['arms'][m];assert arr['items']==ns and arr['tokens']==[costs[k-1] if k else 0 for k in ns]
            hit=[];gr=[];wr=[]
            for k in ns:
                ids=set(series[:k]);h=[len(ids&set(opts))>=atleast for atleast,w,opts in row['groups']];weights=[e[1] for e in row['groups']]
                hit.append(float(all(h) or any(set(opts)<=ids for opts in row['alts'])));gr.append(sum(h)/len(h) if h else 1.)
                wr.append(sum(w*ok for w,ok in zip(weights,h))/sum(weights) if sum(weights) else float(not h))
            assert np.allclose(hit[:4]+gr[:2]+wr[:1]+hit[4:],arr['metric'],rtol=0,atol=1e-12);comps+=1
        blocks[z['repo']].append(q)
    for m,v in s['arms'].items():
        for k,total in enumerate(v['counts']):
            assert math.isclose(sum(out[q]['arms'][m]['metric'][k] for q in pred),total,abs_tol=1e-9)
    repos=sorted(blocks);n=len(repos);assert n==s['repos']==34
    counts=np.array([len(blocks[repo]) for repo in repos]);rng=np.random.default_rng(471018);boot=rng.multinomial(n,np.repeat(1./n,n),size=20000)
    for m,ref in s['contrasts'].items():
        a,b=m.split(' minus ')
        for k in range(9):
            totals=[sum(out[q]['arms'][a]['metric'][k]-out[q]['arms'][b]['metric'][k] for q in blocks[repo]) for repo in repos]
            numer=boot@np.asarray(totals);denom=boot@counts;ci=np.percentile(numer/denom,[2.5,97.5])
            assert np.allclose(ci,[x[k] for x in ref['ci']]) and math.isclose(sum(totals)/sum(counts),ref['micro'][k],abs_tol=1e-12)
    if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in get('manifest.json')['files'].items())
    print('Validated',comps,'complete rankings, nine metrics, six costs and 18 paired 20,000-draw cluster intervals.')
if __name__=='__main__':main()


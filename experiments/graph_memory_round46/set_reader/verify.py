"""Offline scoring verification; all inputs are numeric ordinals or non-source identifiers."""
from pathlib import Path
from itertools import accumulate
from math import isclose,isfinite
import hashlib,gzip,json
D=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256((D/p).read_bytes()).hexdigest()
def get(p):
    b=(D/p).read_bytes();return json.loads(gzip.decompress(b) if p.endswith('.gz') else b)
def main():
    r=get('results.json');j=get('audit-judgments.json.gz');o=get('outcomes.json.gz');f=get('forecasts.json.gz');n=get('reranker-scores.json.gz')
    assert len(j)==len(o)==len(f)==214 and len(n)==12 and r['pred']==sha('forecast-seal.json') and r['outcomes']==sha('outcomes.json.gz') and r['audit']==sha('audit-judgments.json.gz')
    deriv=get('forecast-seal.json');neural=get('reranker-seal.json')
    assert deriv['data']==sha('forecasts.json.gz') and deriv['program']==sha('predict.py') and deriv['core']==sha('core.py') and neural['data']==sha('reranker-scores.json.gz')
    checks=0
    for q,row in j.items():
        methods=f[q]['rank'].copy()
        if q in n:
            view=n[q];idx=methods['qwen'][:16];scores=view['scores'];assert len(scores)==16 and all(isfinite(v) for v in scores.values()) and all(view['indices'][i]==idx[i] for i in range(16))
            methods['neural']=sorted(idx,key=lambda k:(-scores[str(k)],idx.index(k)))+methods['qwen'][16:];assert methods['neural']==view['rank']
        for method,order in methods.items():
            assert sorted(order)==list(range(len(row['cost'])));lens=o[q]['arms'][method]['items'];old=o[q]['arms'][method]
            stack=list(accumulate(row['cost'][s] for s in order));prefix=[sum(x<=cap for x in stack) for cap in (2048,6144)]
            assert lens==[5,8,*[min(8,k) for k in prefix],*prefix]
            assert old['tokens']==[stack[k-1] if k else 0 for k in lens]
            completed=[];frac=[];necessary=[]
            for k in lens:
                chosen=set(order[:k]);group=[len(set(e)&chosen)>=quota for quota,w,e in row['groups']];weights=[w for quota,w,e in row['groups']]
                completed.append(float(all(group) or any(all(e in chosen for e in alt) for alt in row['alternative'])))
                frac.append(sum(group)/len(group) if group else 1.)
                necessary.append(sum(w*c for w,c in zip(weights,group))/sum(weights) if sum(weights) else (0. if group else 1.))
            expect=completed[:4]+frac[:2]+necessary[:1]+completed[4:]
            assert all(isclose(v,w,abs_tol=1e-12) for v,w in zip(expect,old['metric'],strict=True))
            checks+=1
    assert r['native_checks']==2*checks
    if (D/'manifest.json').exists():assert all(sha(k)==v for k,v in get('manifest.json')['files'].items())
    print('Validated',checks,'rankings, 9 outcomes, actual full-source costs, and all 192 small-model comparisons.')
if __name__=='__main__':main()

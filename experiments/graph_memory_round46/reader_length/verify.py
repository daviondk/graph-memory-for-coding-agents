"""No inference: verify all old/new answers and the paired cap-by-policy interaction."""
from collections import Counter
from pathlib import Path
import gzip,hashlib,json,math,re,string
D=Path(__file__).resolve().parent
BASE=D.parent/'reader_transfer'
def read(path):
    raw=path.read_bytes();return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def normalize(s):
    s=''.join(c for c in s.lower() if c not in string.punctuation)
    return re.sub(r'\b(a|an|the)\b',' ',s).split()
def grade(text,refs):
    pred=normalize(text);em=f1=0
    for ref in refs:
        truth=normalize(ref);em=max(em,int(pred==truth))
        overlap=sum((Counter(pred)&Counter(truth)).values())
        f1=max(f1,2*overlap/(len(pred)+len(truth)) if pred or truth else 1)
    return [em,f1]
def close(a,b):return math.isclose(a,b,rel_tol=0,abs_tol=1e-11)
def main():
    m=read(D/'manifest.json')['files'];assert m=={p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name!='manifest.json'}
    r=read(D/'results.json');seal=read(D/'seal.json')
    assert r['previous']==sha(BASE/'manifest.json') and r['answers']==sha(D/'seal.json')
    assert seal['inputs']==sha(BASE/'prompts.json.gz') and seal['answers']==sha(D/'answers.json.gz')
    assert r['outcomes']==sha(D/'outcomes.json.gz') and r['suffixes']==sha(D/'suffixes.json.gz')
    old=read(BASE/'answers.json.gz');new=read(D/'answers.json.gz');ctx=read(BASE/'contexts.json.gz')
    truth=read(BASE/'grading-view.json.gz');out=read(D/'outcomes.json.gz');tails=read(D/'suffixes.json.gz')
    assert set(old)==set(new) and set(ctx)==set(truth)==set(out) and len(new)==1961
    assert set(tails)=={k for k,v in old.items() if v['stop']=='limit'}
    assert all(old[k]['answer']+s==new[k]['answer'] for k,s in tails.items())
    assert sum(old[k]['answer']!=n['answer'] for k,n in new.items())==r['counts']['changed']
    assert all(new[k]['answer']==v['answer'] for k,v in old.items() if v['stop']!='limit')
    count=0;flips=0
    for q,row in ctx.items():
        assert set(row['prompt'])==set(out[q]['arms'])
        for arm,(_,key,n) in row['prompt'].items():
            v=out[q]['arms'][arm];assert v['key']==key and v['input']==n
            for rank,x in [('score24',old[key]),('score96',new[key])]:
                expected=grade(x['answer'],truth[q][0])
                assert all(close(a,b) for a,b in zip(expected,v[rank]))
            count+=1;flips+=not v['same']
    assert count==r['logical']['positions']==4352 and flips==r['logical']['changed']
    for pair,table in r['comparisons'].items():
        a,b=pair.split('-');rows=[v for v in out.values() if a in v['arms'] and b in v['arms']]
        for j,metric in enumerate(('EM','F1')):
            values={str(k):[v['arms'][a][f'score{k}'][j]-v['arms'][b][f'score{k}'][j] for v in rows] for k in (24,96)}
            values['difference']=[x-y for x,y in zip(values['96'],values['24'])]
            for k,delta in values.items():
                v=table[metric][k];assert close(v['pp'],100*sum(delta)/len(delta))
                assert v['n']==len(rows) and v['clusters']==len({s['cluster'] for s in rows})
                assert v['wins']==sum(x>1e-12 for x in delta) and v['losses']==sum(x< -1e-12 for x in delta)
    print('verified both caps:',count,'logical positions,',len(new),'unique generations,',len(tails),'literal continuations')
if __name__=='__main__':main()

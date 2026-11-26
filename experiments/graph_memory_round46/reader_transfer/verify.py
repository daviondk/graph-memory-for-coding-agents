"""Recompute answer metrics and paired effects from the standalone release using Python stdlib."""
import gzip,json,struct,hashlib,re,string
from collections import Counter
from math import isclose
from pathlib import Path
D=Path(__file__).resolve().parent
def get(name):
    b=(D/name).read_bytes();return json.loads(gzip.decompress(b) if name.endswith('.gz') else b)
def sha(name):return hashlib.sha256((D/name).read_bytes()).hexdigest()
def words(s):
    return re.sub(r'\b(a|an|the)\b',' ',''.join(c for c in s.lower() if c not in string.punctuation)).split()
def metrics(text,targets):
    x=words(text);em=f1=0
    for target in targets:
        y=words(target);em=max(em,int(x==y));c=sum(min(x.count(v),y.count(v)) for v in set(x))
        f1=max(f1,2*c/(len(x)+len(y)) if x or y else 1)
    return em,f1
def main():
    assert get('manifest.json')['files']=={p.name:sha(p.name) for p in D.iterdir() if p.is_file() and p.name!='manifest.json'}
    result=get('results.json');ins=get('input-seal.json');out=get('answer-seal.json')
    assert result['gold_slice']==sha('grading-view.json.gz') and result['answers']==sha('answer-seal.json')
    assert out['input']==sha('input-seal.json') and out['answer']==sha('answers.json.gz') and out['replay']==sha('replay.json')
    assert ins['contexts']==sha('contexts.json.gz') and ins['prompts']==sha('prompts.json.gz')
    prompts=get('prompts.json.gz');answers=get('answers.json.gz');ctx=get('contexts.json.gz');obs=get('outcomes.json.gz')
    gold=get('grading-view.json.gz');assert set(prompts)==set(answers) and set(ctx)==set(gold)==set(obs)
    for k,t in prompts.items():assert hashlib.sha256(struct.pack('<'+'I'*len(t),*t)).hexdigest()==k
    assert len(get('replay.json'))==32 and all(v['answer']==answers[k]['answer'] for k,v in get('replay.json').items())
    logical=0
    for q,v in ctx.items():
        assert len({r[-1] for a,r in v['prompt'].items() if a!='closed'})==1
        for a,(second,k,n) in v['prompt'].items():
            em,f=metrics(answers[k]['answer'],gold[q][0]);r=obs[q]['arms'][a]
            assert em==r[0] and isclose(f,r[1],abs_tol=1e-12) and n==len(prompts[k])==r[4]
            assert r[2]==(set(gold[q][1])<=({v['seed'],second} if a!='closed' else set()))
            logical+=1
    for contrast,scores in result['contrasts'].items():
        a,b=contrast.split('-');rows=[r for r in obs.values() if a in r['arms'] and b in r['arms']]
        for j,k in enumerate(['EM','F1','complete_support','contains_answer']):
            delta=[r['arms'][a][j]-r['arms'][b][j] for r in rows];c=scores[k]
            assert isclose(100*sum(delta)/len(delta),c['pp'],abs_tol=1e-11)
            assert c['wins']==sum(v>0 for v in delta) and c['losses']==sum(v<0 for v in delta)
    assert logical==ins['logical']
    print('verified',len(ctx),'questions,',logical,'logical answers,',len(answers),'unique prompts')
if __name__=='__main__':main()

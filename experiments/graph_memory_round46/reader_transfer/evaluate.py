"""Gold reader, official metric, independent reference, paired question/document bootstrap."""
from io46 import *
import sys,re,string
from collections import Counter
sys.path.insert(0,str(AUTHOR))
from metrics.answer import AnswerMetric,compute_f1,compute_exact
import numpy as np

def norm(s):
    s=s.lower().translate(str.maketrans('','',string.punctuation))
    return ' '.join(w for w in re.sub(r'\b(a|an|the)\b',' ',s).split())
def measure(s,ref):
    a,b=norm(s),norm(ref);x,y=a.split(),b.split()
    same=sum((Counter(x)&Counter(y)).values())
    f=2*same/(len(x)+len(y)) if x and y else int(x==y)
    return [int(a==b),f]
def compare(rows,a,b,metric):
    delta=np.array([v['arms'][a][metric]-v['arms'][b][metric] for v in rows])
    t,ix=np.unique([v['cluster'] for v in rows],return_inverse=True)
    def boot(index,seed):
        sizes=np.bincount(index);y=np.bincount(index,weights=delta);rng=np.random.default_rng(seed);z=[]
        for _ in range(100):
            j=rng.integers(len(y),size=(100,len(y)));z.extend(y[j].sum(axis=1)/sizes[j].sum(axis=1))
        return (100*np.quantile(z,[.025,.975])).tolist()
    return dict(pp=delta.mean()*100,cluster=boot(ix,460101),question=boot(np.arange(len(rows)),460102),
                wins=int((delta>0).sum()),losses=int((delta<0).sum()),ties=int((delta==0).sum()),n=len(rows),clusters=len(t))
def means(rows,arms):
    return {k:np.mean([x['arms'][k] for x in rows],axis=0).tolist() for k in arms}
def main():
    receipt=get(D/'answer-seal.json');assert receipt['input']==sha(D/'input-seal.json') and receipt['answer']==sha(D/'answers.json.gz')
    ds=get(D/'delivery-seal.json');assert ds['text']==sha(PRIVATE/'delivered-text.json.gz') and ds['contexts']==receipt['input']
    ctx=get(D/'contexts.json.gz');ans=get(D/'answers.json.gz');texts=get(PRIVATE/'delivered-text.json.gz')
    assert sha(RAW)==get(D/'plan.json')['raw']
    old=get(W/'graph_memory_round33/musique_answers/results.json')['author_sha']
    assert all(sha(AUTHOR/'metrics'/(k+'.py'))==h for k,h in old.items())
    all_arms=(*ARMS,'closed');official={a:AnswerMetric() for a in all_arms};out={};gold_slice={}
    for line in RAW.open(encoding='utf8'):
        row=json.loads(line);q=row['id']
        if q not in ctx:continue
        assert row['answerable']
        item=ctx[q];truth=[row['answer'],*row['answer_aliases']];gold={p['idx'] for p in row['paragraphs'] if p['is_supporting']}
        gold_slice[q]=[truth,sorted(gold)]
        arms={}
        for a,(second,k,n) in item['prompt'].items():
            pred=ans[k]['answer'];official[a](pred,truth)
            ref=[measure(pred,x) for x in truth];em=max(v[0] for v in ref);f1=max(v[1] for v in ref)
            assert em==max(compute_exact(x,pred) for x in truth) and abs(f1-max(compute_f1(x,pred) for x in truth))<1e-12
            docs=texts[k] if a!='closed' else [];addresses={item['seed'],second} if docs else set()
            match=any(' '+norm(x)+' ' in ' '+norm(body)+' ' for x in truth if norm(x) for body in docs)
            arms[a]=[em,f1,int(gold<=addresses),int(match),n,int(norm(pred)=='unknown'),ans[k]['generated']]
        out[q]=dict(cluster=item['cluster'],hops=len(gold),changed=item['prompt']['expanded'][0]!=item['prompt']['mention_expanded'][0],
            equal_input=item['prompt']['expanded'][1]==item['prompt']['mention_expanded'][1],seen_doc=item['seen_doc'],arms=arms)
    assert set(out)==set(ctx);rs=list(out.values());primary=means(rs,ARMS);sub=[v for v in rs if 'closed' in v['arms']]
    for a in all_arms:
        assert np.allclose(official[a].get_metric(),np.mean([v['arms'][a][:2] for v in rs if a in v['arms']],axis=0))
    contrasts={}
    for a,b,part in [('mention_expanded','expanded',rs),('mention_title','title',rs),('mention_expanded','mention_title',rs),
                     ('mention_expanded','closed',sub),('expanded','closed',sub)]:
        contrasts[a+'-'+b]={k:compare(part,a,b,i) for i,k in enumerate(['EM','F1','complete_support','contains_answer'])}
    strata={'change':[v for v in rs if v['changed']],'same':[v for v in rs if not v['changed']],
            'seen_dev_doc':[v for v in rs if v['seen_doc']],'unseen_dev_doc':[v for v in rs if not v['seen_doc']]}
    for h in sorted({v['hops'] for v in rs}):strata[f'{h}hop']=[v for v in rs if v['hops']==h]
    put(D/'outcomes.json.gz',out)
    put(D/'grading-view.json.gz',gold_slice)
    result=dict(n=len(rs),cols=['EM','F1','complete_support','answer_string','prompt_tokens','unknown','generated_tokens'],
        scores=primary,closed_subpanel=means(sub,all_arms),contrasts=contrasts,
        strata={k:[len(v),means(v,ARMS)] for k,v in strata.items() if v},
        equal_exact_prompts=sum(v['equal_input'] for v in rs),distinct_primary_docs=sum(v['changed'] for v in rs),
        gold=sha(RAW),gold_slice=sha(D/'grading-view.json.gz'),grader=sha(D/'evaluate.py'),
        outcomes=sha(D/'outcomes.json.gz'),answers=sha(D/'answer-seal.json'))
    put(D/'results.json',result)
    print(result['scores']);print({k:v['F1'] for k,v in contrasts.items()})

if __name__=='__main__':main()

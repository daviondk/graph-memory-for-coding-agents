"""Compare both caps on identical real prompts after the new answers are sealed."""
from collections import Counter,defaultdict
from pathlib import Path
import sys
import numpy as np
D=Path(__file__).resolve().parent
PREV=D.parent/'reader_transfer'
sys.path.insert(0,str(PREV))
from io46 import get,sha,put,ARMS,AUTHOR
from verify import metrics as independent_metrics
sys.path.insert(0,str(AUTHOR))
from metrics.answer import AnswerMetric,compute_exact,compute_f1

def interval(values,clusters):
    groups,ix=np.unique(clusters,return_inverse=True)
    totals=np.bincount(ix,weights=values);freq=np.bincount(ix)
    rng=np.random.default_rng(460101);results=[]
    for _ in range(100):
        draws=rng.integers(len(freq),size=(100,len(freq)))
        results.extend(totals[draws].sum(axis=1)/freq[draws].sum(axis=1))
    return list(100*np.quantile(results,[.025,.975]))

def comparison(y,clusters):
    values=np.array(y)
    wins=int(np.count_nonzero(values>1e-12));losses=int(np.count_nonzero(values< -1e-12))
    return dict(pp=float(100*values.mean()),ci=interval(values,clusters),n=len(values),
        clusters=len(set(clusters)),wins=wins,losses=losses,ties=len(values)-wins-losses)

def run():
    seal=get(D/'seal.json');transfer=get(PREV/'manifest.json')['files']
    for name in ['contexts.json.gz','answers.json.gz','grading-view.json.gz','outcomes.json.gz','plan.json','prompts.json.gz','verify.py']:
        assert sha(PREV/name)==transfer[name]
    assert seal['protocol']==sha(D/'PROTOCOL_RU.md') and seal['answers']==sha(D/'answers.json.gz')
    plan=get(PREV/'plan.json');assert (seal['model'],seal['server'])==(plan['model'],plan['server'])
    assert seal['inputs']==sha(PREV/'prompts.json.gz')
    old=get(PREV/'answers.json.gz');new=get(D/'answers.json.gz');assert set(old)==set(new) and len(new)==seal['size']==1961
    api_hashes=get(PREV.parents[1]/'graph_memory_round33/musique_answers/results.json')['author_sha']
    assert all(sha(AUTHOR/'metrics'/(k+'.py'))==v for k,v in api_hashes.items())
    live=Counter();sfx={};char_counts=[];stops=defaultdict(Counter)
    for k,v in old.items():
        cur=new[k];a,b=v['answer'],cur['answer'];old_limit=v['stop']=='limit';new_limit=cur['stop']=='limit'
        live.update(dict(unique=1,old_limit=old_limit,new_limit=new_limit,old_tokens=v['generated'],new_tokens=cur['tokens'],
            old_below_24=v['generated']<24,changed=a!=b,old_below_24_changed=(v['generated']<24 and a!=b),
            changed_from_limited=old_limit and a!=b,changed_from_natural=not old_limit and a!=b,
            old_natural_at24=not old_limit and v['generated']==24,old_limit_prefix=old_limit and b.startswith(a),
            extended=len(b)>len(a) and b.startswith(a)))
        stops[v['stop']][cur['stop']]+=1
        if b.startswith(a) and old_limit:
            suffix=b[len(a):];sfx[k]=suffix;char_counts.append(len(suffix))
    # Output strings were stripped by both servers. The observed prefix is compared as a string.
    put(D/'suffixes.json.gz',sfx)
    ctx=get(PREV/'contexts.json.gz');gold=get(PREV/'grading-view.json.gz');baseline=get(PREV/'outcomes.json.gz')
    out={};meters={};logical=Counter()
    for q,r in ctx.items():
        labels=gold[q][0];arms={}
        for arm,(_,key,tokens_in) in r['prompt'].items():
            streams=[];v=old[key];n=new[key]
            for cap,text in ((24,v['answer']),(96,n['answer'])):
                official=[max(compute_exact(t,text) for t in labels),max(compute_f1(t,text) for t in labels)]
                independent=independent_metrics(text,labels)
                assert np.allclose(official,independent,rtol=0,atol=1e-12)
                meters.setdefault((cap,arm),AnswerMetric())(text,labels)
                streams.append(official)
            assert np.allclose(streams[0],baseline[q]['arms'][arm][:2],atol=1e-12)
            arms[arm]=dict(key=key,score24=streams[0],score96=streams[1],
                    tokens=[v['generated'],n['tokens']],limit=[v['stop']=='limit',n['stop']=='limit'],
                    same=v['answer']==n['answer'],prefix=n['answer'].startswith(v['answer']),input=tokens_in)
            logical.update(dict(positions=1,changed=v['answer']!=n['answer'],old_limit=v['stop']=='limit',new_limit=n['stop']=='limit'))
        out[q]=dict(cluster=r['cluster'],arms=arms)
    assert logical['positions']==4352
    groups={};comparisons={}
    for arm in (*ARMS,'closed'):
        subset=[v for v in out.values() if arm in v['arms']]
        rows=[v['arms'][arm] for v in subset]
        groups[arm]=dict(n=len(rows),caps={},changed=sum(not r['same'] for r in rows))
        for j,cap in enumerate((24,96)):
            raw=np.array([r[f'score{cap}'] for r in rows])
            assert np.allclose(meters[cap,arm].get_metric(),raw.mean(axis=0),rtol=0,atol=1e-12)
            groups[arm]['caps'][str(cap)]=dict(em=raw[:,0].mean(),f1=raw[:,1].mean(),
                output_tokens=np.mean([r['tokens'][j] for r in rows]),limited=sum(r['limit'][j] for r in rows))
        groups[arm]['change']={name:comparison([r['score96'][j]-r['score24'][j] for r in rows],[v['cluster'] for v in subset])
                              for j,name in enumerate(('EM','F1'))}
    for a,b in [('mention_expanded','expanded'),('mention_title','title'),('mention_expanded','closed'),('expanded','closed')]:
        rs=[v for v in out.values() if b in v['arms'] and a in v['arms']];cl=[v['cluster'] for v in rs]
        values={}
        for j,metric in enumerate(('EM','F1')):
            effect={cap:np.array([v['arms'][a][f'score{cap}'][j]-v['arms'][b][f'score{cap}'][j] for v in rs]) for cap in (24,96)}
            values[metric]={str(cap):comparison(y,cl) for cap,y in effect.items()}
            values[metric]['difference']=comparison(effect[96]-effect[24],cl)
        comparisons[a+'-'+b]=values
    # Nested 256-question control deserves same-denominator means.
    closed=[v for v in out.values() if 'closed' in v['arms']]
    panel={arm:np.mean([v['arms'][arm]['score96'] for v in closed],axis=0).tolist() for arm in (*ARMS,'closed')}
    put(D/'outcomes.json.gz',out)
    result=dict(counts=live,logical=logical,groups=groups,comparisons=comparisons,closed_subset_96=panel,
        stop_transitions=stops,extra_characters=dict(total=sum(char_counts),median=float(np.median(char_counts)),max=max(char_counts)),
        answers=sha(D/'seal.json'),previous=sha(PREV/'manifest.json'),outcomes=sha(D/'outcomes.json.gz'),
        suffixes=sha(D/'suffixes.json.gz'),analysis=sha(D/'analyze.py'),bootstrap=dict(replicates=10000,seed=460101))
    put(D/'results.json',result)
    print('primary',comparisons['mention_expanded-expanded'],'counts',live,logical)

if __name__=='__main__':run()

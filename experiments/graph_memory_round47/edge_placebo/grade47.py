"""Independent computation and official AnswerMetric; paired intervals over whole first-doc clusters."""
from collections import Counter
import numpy as np
from base47 import *
from io46 import AUTHOR
from evaluate import norm,measure
sys.path.insert(0,str(AUTHOR))
from metrics.answer import AnswerMetric,compute_exact,compute_f1

def contrast(delta,cluster):
    # delta[question, graph-permutation, metric]; same replicate of each graph is used by all questions.
    unique,ix=np.unique(cluster,return_inverse=True);count=np.bincount(ix)
    acc=np.zeros((len(unique),*delta.shape[1:]));np.add.at(acc,ix,delta)
    rng=np.random.default_rng(470091);rb=np.random.default_rng(470092);fixed=[];cross=[]
    for _ in range(100):
        ts=rng.integers(len(unique),size=(100,len(unique)))
        w=np.stack([np.bincount(t,minlength=len(unique)) for t in ts])
        total=(w@acc.reshape(len(unique),-1)).reshape(100,*delta.shape[1:])/(w@count)[:,None,None]
        fixed.extend(total.mean(axis=1))
        seeds=rb.integers(len(SEEDS),size=(100,len(SEEDS)))
        cross.extend(total[np.arange(100)[:,None],seeds].mean(axis=1))
    def ci(records):return (100*np.quantile(records,[.025,.975],axis=0).T).tolist()
    question=delta.mean(axis=1)
    return dict(n=len(ix),clusters=len(unique),pp=(100*question.mean(axis=0)).tolist(),
        cluster_ci=ci(fixed),cluster_seed_ci=ci(cross),per_seed=(100*delta.mean(axis=0)).tolist(),
        wins=(question>1e-12).sum(axis=0).tolist(),losses=(question< -1e-12).sum(axis=0).tolist())

def unit(q,truth,ids,dctx,docs,full):
    out={}
    for a,(target,k,n) in dctx['refs'].items():
        answer=full[k]['answer'];calc=[measure(answer,v) for v in truth]
        em=max(z[0] for z in calc);f1=max(z[1] for z in calc)
        assert em==max(compute_exact(v,answer) for v in truth) and abs(f1-max(compute_f1(v,answer) for v in truth))<1e-12
        present=any(' '+norm(v)+' ' in ' '+norm(text)+' ' for v in truth if norm(v) for text in docs[k])
        out[a]=[em,f1,int(set(ids)<={dctx['seed'],target}),int(present),n,full[k]['tokens']]
    return out

def analyze(rows):
    if not rows:return None
    a=np.array([[[r['arms'][x][i] for i in range(4)] for x in ARMS] for r in rows])
    true=a[:,[0]];base=a[:,[1]];sham=a[:,2:];c=[r['cluster'] for r in rows]
    return dict(n=len(rows),means={'true':true.mean(axis=(0,1)).tolist(),'sham':sham.mean(axis=(0,1)).tolist(),
        'lex':base.mean(axis=(0,1)).tolist()},contrasts={k:contrast(d,c) for k,d in [
        ('true-sham',true-sham),('sham-lex',sham-base),('true-lex',np.broadcast_to(true-base,sham.shape))]})

def main():
    check();seal=get(D/'answer-seal.json');assert seal['input']==sha(D/'input-seal.json') and seal['answers']==sha(D/'answers.json.gz')
    inputs=get(D/'input-seal.json');assert inputs['texts']==sha(P47/'delivered.json.gz') and inputs['contexts']==sha(D/'contexts.json.gz')
    full=get(D/'answers.json.gz');ctx=get(D/'contexts.json.gz');docs=get(P47/'delivered.json.gz')
    gold=signed(R46,'grading-view.json.gz');old=signed(LONG,'outcomes.json.gz');hist=signed(R46,'contexts.json.gz')
    assert set(ctx)==set(gold)
    meters={a:AnswerMetric() for a in ARMS};out={};stable=0
    for q,v in ctx.items():
        truth,ids=gold[q];scores=unit(q,truth,ids,v,docs,full)
        for a,(_,k,_) in v['refs'].items():meters[a](full[k]['answer'],truth)
        if v['n']==v['original_n']:
            for a,arm in [('true','mention_expanded'),('lex','expanded')]:
                assert v['refs'][a][1]==hist[q]['prompt'][arm][1]
                assert np.allclose(scores[a][:2],old[q]['arms'][arm]['score96'],rtol=0,atol=1e-12)
                stable+=1
        out[q]=dict(cluster=v['cluster'],switch=v['switch'],successful=v['successful'],
                    shortened=v['n']!=v['original_n'],arms=scores)
    rs=list(out.values())
    for a,m in meters.items():assert np.allclose(m.get_metric(),np.mean([r['arms'][a][:2] for r in rs],axis=0),rtol=0,atol=1e-12)
    groups={'all':analyze(rs),'switched':analyze([r for r in rs if r['switch']]),'substituted':analyze([r for r in rs if r['successful']])}
    orders=get(D/'orders.json.gz');profile={};distances=[]
    for s in SEEDS:
        drawn=[];rqdist=[];reddist=[];overlap=Counter()
        for q,r in orders.items():
            sim=r['sham'][str(s)];t=r['true'];f=sim['second'];e=r['order'];oldedges=set(r['edges']);newedges=set(sim['edges'])
            overlap.update(dict(real_links=len(oldedges),sham_links=len(newedges),shared=len(oldedges&newedges),
                               switched=t!=r['lex'],substituted=t!=f))
            if t!=f:
                drawn.append(e.index(f)-e.index(t));rqdist.append(abs(r['question_rank'][str(f)]-r['question_rank'][str(t)]))
                reddist.append(abs(r['snippet_rank'][str(f)]-r['snippet_rank'][str(t)]))
        distances+=drawn
        profile[str(s)]={**overlap,'mean_rank_delta':float(np.mean(drawn)),'median_abs_rank_delta':float(np.median(np.abs(drawn))),
            'mean_question_abs':float(np.mean(rqdist)),'mean_snippet_abs':float(np.mean(reddist))}
    lengths=[v['refs']['true'][2] for v in ctx.values()]
    put(D/'outcomes.json.gz',out)
    put(D/'results.json',dict(groups=groups,metrics=['EM','F1','complete_support','answer_string'],profiles=profile,stable=stable,
        all_rank_abs_median=float(np.median(np.abs(distances))),all_rank_abs_p95=float(np.quantile(np.abs(distances),.95)),
        mean_input=float(np.mean(lengths)),shortened=sum(v['shortened'] for v in rs),answers=sha(D/'answer-seal.json'),
        outcomes=sha(D/'outcomes.json.gz'),grader=sha(D/'grade47.py'),bootstrap=10000,
        observed_wp_limit=192,cap96=True))
    print(groups['all']['means']);print(groups['all']['contrasts']['true-sham'])
if __name__=='__main__':main()

"""Score sealed full-corpus predictions and cross-check official evaluator outputs."""
import ast
from collections import Counter
import collections
from concurrent.futures import ThreadPoolExecutor
import csv,io,json,math
import numpy as np
from source import ROOT,R8,CACHE,base,member,load_json,write_json,h
from predict import METHODS
from typing import Optional

def metric(positions,n,ks=(5,10,15)):
    rr=min(positions,default=10**8)
    values={'mrr10':1/rr if rr<=10 else 0,'hit10':int(rr<=10)}
    for k in ks:
        found=[r for r in positions if r<=k]
        values['acc'+str(k)]=int(len(found)==n)
        values['recall'+str(k)]=len(found)/n
    dcg=sum(1/math.log2(1+r) for r in positions if r<=10)
    values['ndcg10']=dcg/sum(1/math.log2(1+r) for r in range(1,1+min(10,n)))
    return values
def canon(s):
    file,func=s.split('.py/')
    return file+'.py:'+func.removesuffix('.__init__').strip('/').replace('/','.')
def labels(t):
    data=member(base(t)+'qrels/test.tsv')
    rows=list(csv.DictReader(io.StringIO(data.decode()),delimiter='\t'))
    assert all(r['query-id']==t for r in rows)
    assert all(float(r['score'])>0 for r in rows)
    return (t,sorted({r['corpus-id'] for r in rows}),h(data))
def sign(w,l):
    n=w+l
    return min(1.,2*sum(math.comb(n,k) for k in range(min(w,l)+1))/(2**n)) if n else 1.
def compare(diff,ix):
    vals=np.asarray(diff)
    sims=vals[ix].mean(1)
    w=int(np.sum(vals>1e-12));l=int(np.sum(vals< -1e-12))
    return {'delta':float(vals.mean()),'lo':float(np.quantile(sims,.025)),'hi':float(np.quantile(sims,.975)),'w':w,'tie':len(vals)-w-l,'l':l,'exact_p':sign(w,l)}
def orig_scorer():
    import torch
    from torch import Tensor
    expected='11a886e0d12895dca9c3eef03ddd1c4282adab94e771089814ab7516c936c03d'
    source=(CACHE/'refactored_eval_localization.py').read_bytes()
    assert h(source)==expected
    # Only import the authors' specified metric/data functions; their unused optional LLM dependencies aren't needed.
    whitelist={'load_jsonl','convert_solutions_dict','_dcg','div_no_nan','normalized_dcg','recall_at_k','acc_at_k','cal_metrics_w_dataset'}
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in whitelist]
    env=dict(torch=torch,Tensor=Tensor,Optional=Optional,collections=collections,json=json)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'pinned_swerank_evaluator','exec'),env)
    env['METRIC_FUNC']={'acc':env['acc_at_k'],'recall':env['recall_at_k'],'ndcg':env['normalized_dcg']}
    env['METRIC_NAME']={'acc':'Acc','recall':'Recall','ndcg':'NDCG'}
    return env['cal_metrics_w_dataset'],expected
def main():
    seal=load_json(ROOT/'blind_seal.json')
    assert all(h((ROOT/p).read_bytes())==v for p,v in seal['local'].items())
    assert all(h((R8/p).read_bytes())==v for p,v in seal['r8'].items())
    sample=load_json(ROOT/'sample.json')['selected']
    with ThreadPoolExecutor(max_workers=8) as pool:
        j=list(pool.map(labels,[r['issue'] for r in sample]))
    write_json(ROOT/'judgments.json',j)
    gold={t:set(g) for t,g,_ in j}
    meter={};details={}
    for row in sample:
        t=row['issue'];g=gold[t]
        r=load_json(ROOT/'predictions'/(t+'.json'))
        if not g:continue
        names={canon(s) for s in g}
        base10={canon(s) for s in r['ranks']['dense'][:10]}
        bym={}
        for m in METHODS:
            ranking=r['ranks'][m]
            assert len(ranking)==len(set(ranking))==row['functions']
            canonical=[canon(s) for s in ranking]
            assert len(canonical)==len(set(canonical)),(t,'duplicate normalized function label')
            result=metric([i+1 for i,s in enumerate(canonical) if s in names],len(names))
            proposed={canon(s) for s in r['suggestions'][m]}
            top_10=set(canonical[:10])
            result.update(extra_reads=len(proposed),seed_reads=6 if m in ['one','corroborated','two_callers','matched'] else 0,new_correct=sum(p in names for p in proposed),removed_correct=len((base10-top_10)&names),returned_correct=len(top_10&names))
            bym[m]=result
        details[t]={'band':row['band'],'n_gold':len(names),'n_corpus':row['functions'],'gold_in_corpus':sum(canon(s) in names for s in r['ranks']['dense']),'seed_bytes':r['seed_bytes'],'seed_wordpieces':r['seed_wordpieces'],'failed_seed_ast':len(r['failed_seed_ast']),'stored_edges':len(r['stored_edges']),'edge_bytes':r['serialized_triple_bytes'],'methods':bym}
    tids=list(details)
    assert tids
    bands=sorted({d['band'] for d in details.values()})
    ix=np.concatenate([np.random.default_rng(91108+i).choice([j for j,t in enumerate(tids) if details[t]['band']==b],size=(10000,sum(details[t]['band']==b for t in tids)),replace=True) for i,b in enumerate(bands)],axis=1)
    keys=list(details[tids[0]]['methods']['dense'])
    means={m:{v:float(np.mean([details[t]['methods'][m][v] for t in tids])) for v in keys} for m in METHODS}
    contrasts={}
    for a,b in [('corroborated',m) for m in METHODS if m!='corroborated']+[('one','dense'),('ids','dense')]:
        contrasts[a+'-'+b]={v:compare([details[t]['methods'][a][v]-details[t]['methods'][b][v] for t in tids],ix) for v in keys}
    scorer,sha=orig_scorer();official={}
    out=ROOT/'official_inputs';out.mkdir(exist_ok=True)
    qrels=[{t:{s:1 for s in g}} for t,g in gold.items() if g]
    for m in METHODS:
        p=out/(m+'.jsonl')
        with p.open('w',encoding='utf8') as f:
            for t in tids:
                rank=load_json(ROOT/'predictions'/(t+'.json'))['ranks'][m]
                print(json.dumps({'instance_id':t,'docs':rank[:max(15,min(100,len(rank)))]}),file=f)
        res=scorer(str(p),'docs','function','loc-bench','test',[5,10,15],['acc','recall','ndcg'],qrels=qrels)
        official[m]=res
    nulls=[pair for t in tids for pair in load_json(ROOT/'predictions'/(t+'.json'))['null_pairs']]
    diagnostic={'judged':len(tids),'unjudged':len(sample)-len(tids),'n_gold_total':sum(d['n_gold'] for d in details.values()),'more_than_15':sum(d['n_gold']>15 for d in details.values()),'null_pairs':len(nulls),'matched_both_bins':sum(p['same_degree_bin'] and p['same_rank_bin'] for p in nulls),'trigger':{m:sum(d['methods'][m]['extra_reads']>0 for d in details.values()) for m in METHODS},'official_scorer_sha256':sha,'maximum_absolute_acc10_rounding_difference':max(abs(official[m]['Acc@10']-means[m]['acc10']) for m in METHODS)}
    write_json(ROOT/'results.json',dict(diagnostics=diagnostic,means=means,contrasts=contrasts,official=official,details=details))
    with (ROOT/'per_issue.csv').open('w',encoding='utf8',newline='') as hand:
        w=csv.DictWriter(hand,fieldnames=['issue','band','method','n_corpus','n_gold']+keys);w.writeheader()
        for t,d in details.items():
            for m,z in d['methods'].items():w.writerow({'issue':t,'band':d['band'],'method':m,'n_corpus':d['n_corpus'],'n_gold':d['n_gold'],**z})
    print(diagnostic)
    for m in METHODS:print(m,*(round(means[m][v],3) for v in ['acc10','recall10','mrr10','extra_reads']))
    print(contrasts['corroborated-dense']['acc10'])
if __name__=='__main__':main()

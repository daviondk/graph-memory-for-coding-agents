"""Join published labels only after the blind prediction and input locks verify."""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
import numpy as np
from generate import HERE, SRC, hash_file, read, save, utc

METRICS = ['match1','hit5','rr','recall5']


def csv_rows(path):
    with path.open(encoding='utf-8-sig',newline="") as f:
        return list(csv.DictReader(f))


def exact_p(wins,losses):
    n=wins+losses
    return min(1,2*sum(math.comb(n,i) for i in range(min(wins,losses)+1))/2**n)


def repo_boot(indices, repos):
    by=defaultdict(list)
    for pos,index in enumerate(indices):
        by[repos[index]].append(pos)
    j=list(by)
    arr=np.zeros((len(by),len(indices)),dtype=np.int32)
    for k,name in enumerate(j):
        arr[k,by[name]]=1
    rng=np.random.default_rng(20261116)
    picks=rng.integers(low=0,high=len(j),size=(10000,len(j)))
    weights=np.zeros((10000,len(j)),dtype='int32')
    for n in range(len(j)):
        weights[:,n]=(picks==n).sum(axis=1)
    return arr,weights


def bounds(d,groups,weights):
    counts=groups.sum(axis=1)
    samples=(weights@(groups@d))/(weights@counts)
    return np.quantile(samples,[.025,.975]).tolist()


def paired(v,groups,weights,binary):
    result={'delta':float(np.mean(v)), 'repo_ci95':bounds(v,groups,weights)}
    if binary:
        a=int((v>0).sum()); b=int((v<0).sum())
        result.update(wins=a,losses=b,mcnemar_exact_p=exact_p(a,b))
    return result


def main():
    lock=read(HERE/'predictions-lock.json')
    assert all(hash_file(HERE/key)==sha for key,sha in lock['files'].items())
    assert read(HERE/'design-lock.json')['files']['original/blind_ranks.json']==hash_file(SRC/'blind_ranks.json')
    with np.load(HERE/'rankings.npz',allow_pickle=False) as data:
        predictions={name:data[name] for name in data.files}
    keys=read(HERE/'keys.json')
    library={r['trace_key']:r['instance_id'] for r in csv_rows(SRC/'evaluation_library.csv')}
    assert len(set(library.values()))==len(library)==len(keys)==300 and set(keys)==set(library)
    gold=defaultdict(set)
    for row in csv_rows(SRC/'evaluation_relations.csv'):
        gold[row['related_instance_id']].add(row['experience_instance_id'])
    metadata=csv_rows(SRC/'per_query.csv')
    assert [int(r['ordinal']) for r in metadata]==list(range(357))
    assert [r['group'] for r in metadata]==['lite']*99+['extension']*258
    positions={library[key]:i for i,key in enumerate(keys)}
    data,query_rows,scoring_inputs={},[],[]
    for name,rank in predictions.items():
        assert np.array_equal(np.sort(rank,axis=1),np.tile(np.arange(len(keys)),(len(metadata),1)))
        data[name]=np.zeros((len(metadata),4),dtype=np.float64)
    repos=[r['repo'] for r in metadata]
    for i,r in enumerate(metadata):
        truth=gold[r['instance_id']]
        assert truth==set(r['gold_ids'].split('|')) and bool(truth)
        available=[positions[k] for k in sorted(truth) if k in positions]
        scoring_inputs.append({'ordinal':i,'associated_library_indices':available,'n_valid_relations':len(truth)})
        assert bool(available)==bool(int(r['available']))
        detail={'ordinal':i,**{k:r[k] for k in ['repo','group','instance_id','gold_ids','available']}}
        for name,rank in predictions.items():
            pos=np.where(np.isin(rank[i],available))[0]+1
            n5=int(sum(pos<=5))
            first=int(pos[0]) if len(pos) else None
            v=[int(first==1),int(n5>0),1/first if first else 0,n5/len(truth)]
            data[name][i]=v
            detail.update({name+"_"+k:x for k,x in zip(METRICS,v)})
            detail[name+"_rank"]=first if first else ''
        query_rows.append(detail)
    save('scoring-inputs.json',scoring_inputs)
    with (HERE/'per_query.csv').open("w",newline="",encoding='utf8') as f:
        w=csv.DictWriter(f,list(query_rows[0]));w.writeheader();w.writerows(query_rows)
    groups={'lite':list(range(99)),'extension':list(range(99,357)),
            'extension_available':[i for i in range(99,357) if int(metadata[i]['available'])]}
    estimates={}
    for group,idx in groups.items():
        rmap,weights=repo_boot(idx,repos)
        measures={}
        for name,x in data.items():
            sample=x[idx]
            measures[name]={'match1':int(sample[:,0].sum()),'hit5':int(sample[:,1].sum()),'mrr':float(sample[:,2].mean()),'macro_recall5':float(sample[:,3].mean())}
        comparisons={}
        for backend in ('hyb','lex'):
            base=backend+'_real'
            for other in (backend+'_absent',backend+'_shuffle'):
                diff=(data[base]-data[other])[idx]
                comparisons[f'{base}-{other}']={k:paired(diff[:,j],rmap,weights,j<2) for j,k in enumerate(METRICS)}
        both=(data['hyb_real']-data['hyb_absent']-data['lex_real']+data['lex_absent'])[idx,1]
        estimates[group]={'n':len(idx),'repos':rmap.shape[0],'available':sum(int(metadata[i]['available']) for i in idx),
                          'methods':measures,'paired':comparisons,'hit5_interaction':paired(both,rmap,weights,False)}
    confirm=estimates['lite']['paired']
    tests=sorted((confirm[name]['hit5']['mcnemar_exact_p'],name) for name in ('hyb_real-hyb_absent','hyb_real-hyb_shuffle'))
    lower=0
    for j,(p,name) in enumerate(tests):
        lower=max(lower,min(1,(len(tests)-j)*p))
        confirm[name]['hit5']['holm_pair_p']=lower
    save('results.json',{'utc':utc(),'cohorts':estimates,'primary':'lite/hyb_real-hyb_absent and lite/hyb_real-hyb_shuffle on hit5',
        'blind_predictions_sha256':lock['files']['rankings.npz'],'score_script_sha256':hash_file(Path(__file__)),
        'label_source_sha256':{f:hash_file(SRC/f) for f in ['evaluation_library.csv','evaluation_relations.csv','per_query.csv']}})
    print(json.dumps(estimates['lite']['methods'],indent=1))

if __name__=='__main__':
    main()


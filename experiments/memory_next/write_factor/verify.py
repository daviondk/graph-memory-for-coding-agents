"""Recompute all 2,142 query decisions from the frozen rank matrix, without models or original dataset."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def j(name):
    return json.loads((HERE/name).read_text(encoding='utf8'))


def verify():
    lock=j('predictions-lock.json')['files']
    for name,sha in lock.items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==sha,name
    rows=list(csv.DictReader((HERE/'per_query.csv').open(encoding='utf8',newline='')))
    labels=j('scoring-inputs.json')
    metrics=j('results.json')['cohorts']
    with np.load(HERE/'rankings.npz',allow_pickle=False) as r:
        assert len(rows)==len(labels)==357
        for name in r.files:
            totals={k:[] for k in metrics}
            for i,(stored,lbl) in enumerate(zip(rows,labels)):
                assert int(stored['ordinal'])==lbl['ordinal']==i
                rank=r[name][i].tolist()
                assert sorted(rank)==list(range(300))
                positions=[rank.index(card)+1 for card in set(lbl['associated_library_indices'])]
                first=min(positions,default=0)
                count=sum(v<=5 for v in positions)
                cell=[int(first==1),int(count>0),1/first if first else 0,count/lbl['n_valid_relations']]
                assert stored[name+'_rank']==(str(first) if first else '')
                assert cell==[float(stored[name+'_'+f]) for f in ['match1','hit5','rr','recall5']]
                totals[stored['group']].append(cell)
                if stored['group']=='extension' and bool(positions):totals['extension_available'].append(cell)
            for group,obs in totals.items():
                measured=metrics[group]['methods'][name];m=np.array(obs)
                assert len(obs)==metrics[group]['n'] and int(m[:,0].sum())==measured['match1'] and int(m[:,1].sum())==measured['hit5']
                assert np.allclose(m[:,2:].mean(axis=0),[measured['mrr'],measured['macro_recall5']],atol=1e-12,rtol=0)
    print('All six full rankings and all 2,142 outcomes verified across three reported populations.')


if __name__=='__main__':verify()


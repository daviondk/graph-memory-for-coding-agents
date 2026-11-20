"""Pair all predictions with hidden future-file membership and resample whole repositories."""
from collections import defaultdict
import gzip
import json
import numpy as np
from retain import ROOT, METHODS, save, sha

def load(name):return json.loads(gzip.decompress((ROOT/name).read_bytes()))
def main():
    lock=json.loads((ROOT/'decision_lock.json').read_bytes())
    for n,h in lock['hashes'].items():assert sha((ROOT/n).read_bytes())==h,n
    rows=load('decisions.json.gz');gold={(r['repo'],r['issue']):set(r['keys']) for r in load('gold.json.gz')}
    assert len(rows)==len(gold)==lock['n']
    scores=defaultdict(list);ceil=[];out=[]
    for r in rows:
        true=gold[r['repo'],r['issue']]
        ceil.append(bool(true.intersection(r['seen'])))
        trial={'repo':r['repo'],'issue':r['issue'],'past_has_target':ceil[-1],'methods':{}}
        for p,record in r['policies'].items():
            n=len(true.intersection(record['keys']))
            s=[int(n>0),n/len(true),record['added'],len(record['keys'])]
            scores[p].append(s);trial['methods'][p]=s
        out.append(trial)
    summary={p:dict(hits=int(np.sum(s,axis=0)[0]),hit_rate=float(np.mean(s,axis=0)[0]),mean_recall=float(np.mean(s,axis=0)[1]),cumulative_pointer_admissions=int(np.sum(s,axis=0)[2]),read_pointers=int(np.sum(s,axis=0)[3])) for p,s in scores.items()}
    repos=sorted({r['repo'] for r in rows});idx=np.random.default_rng(18112026).integers(len(repos),size=(10000,len(repos)))
    contrasts={}
    for m in METHODS:
        v=np.asarray(scores['3/'+m])[:,0]-np.asarray(scores['3/confirmation'])[:,0]
        totals=np.array([[sum(v[i] for i,r in enumerate(rows) if r['repo']==repo),sum(r['repo']==repo for r in rows)] for repo in repos])
        d=totals[idx].sum(axis=1)
        contrasts[m]={'wins':int(sum(v>0)),'losses':int(sum(v<0)),'delta':v.mean(),'repo_paired_ci':np.quantile(d[:,0]/d[:,1],[.025,.975]).tolist(),'different_predictions':sum(r['policies']['3/'+m]['keys']!=r['policies']['3/confirmation']['keys'] for r in rows)}
    result={'n':len(rows),'eligible_positions':lock['eligible_positions'],'repos':len(repos),'any_history_hits':sum(ceil),'methods':summary,'contrasts_vs_confirmation_at_three':contrasts}
    save('scores.json.gz',out);save('results.json',result)
    print('n/repos/ceiling',len(rows),len(repos),sum(ceil))
    print('3 slots',[(m,summary['3/'+m]['hits'],contrasts[m]['wins'],contrasts[m]['losses'],summary['3/'+m]['cumulative_pointer_admissions']) for m in METHODS])
    print('primary',contrasts['protect'])
if __name__=='__main__':main()

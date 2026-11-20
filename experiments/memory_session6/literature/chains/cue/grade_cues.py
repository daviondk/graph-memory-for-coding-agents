"""Join future edit membership only to locked decisions; paired whole-repo inferential units."""
from collections import Counter
import itertools
import numpy as np
from common import HERE,WRITE,digest,ident,load,save

def summarize(scores,decisions,methods):
    repos=sorted({r['repo'] for r in scores});rid={v:i for i,v in enumerate(repos)}
    cluster=np.asarray([rid[r['repo']] for r in scores])
    draws=np.random.default_rng(18112026).integers(len(repos),size=(10000,len(repos)))
    counts=np.bincount(cluster,minlength=len(repos))
    n=len(scores);assert n==374 and len(repos)==77
    reachable=np.asarray([r['available'] for r in scores])
    result={'n':n,'repos':len(repos),'reachable':int(reachable.sum()),'methods':{},'contrasts':{},
            'resident_entries':sum(len(r['candidates']) for r in decisions),
            'candidate_counts':{str(k):v for k,v in sorted(Counter(len(r['candidates']) for r in decisions).items())},
            'prefix_lengths':{str(k):v for k,v in sorted(Counter(r['prefix'] for r in decisions).items())},
            'stable_changed_some_record':sum(bool(r['differing_stable_vs_latest_records']) for r in decisions),
            'stable_changed_records':sum(r['differing_stable_vs_latest_records'] for r in decisions),
            'historical_pointer_admissions':sum(r['admissions'] for r in decisions),
            'stable_prior_words_scanned':sum(r['stable_prior_word_ids_scanned'] for r in decisions),
            'path_terms_across_queries':sum(r['resident_path_terms'] for r in decisions),
            'logical_query_terms':sum(r['issue_word_ids'] for r in decisions),
            'max_repo_n':int(max(counts))}
    for m in methods:
        v=np.asarray([r['hit'][m] for r in scores],dtype=int)
        rows=[r['methods'][m] for r in decisions];words=[r['cue_ids'] for r in rows]
        result['methods'][m]=dict(hits=int(v.sum()),rate=v.mean(),reads=n,
            hits_per_reachable=float(v[reachable].mean()),cue_ids_total=sum(words),cue_ids_mean=float(np.mean(words)),cue_ids_max=max(words),
            bytes_mean_96bit=float(np.mean(words)*12),bytes_max_96bit=max(words)*12,
            historical_new_word_writes=sum(r['words_written'] for r in rows),
            ambiguous_top=sum(r['top_ties']>1 for r in rows),top_score_zero=sum(r['top_score']==0 for r in rows))
    primary=[('stable8','latest8'),('stable8','path'),('latest8','path'),('uniform8','path'),('full_latest','path'),('path','recency')]
    pairs=primary+[(a,b) for a,b in itertools.combinations(reversed(methods),2) if (a,b) not in primary and (b,a) not in primary]
    assert len(pairs)==15
    for a,b in pairs:
        av=np.asarray([r['hit'][a] for r in scores],dtype=int);bv=np.asarray([r['hit'][b] for r in scores],dtype=int)
        v=av-bv;g=np.bincount(cluster,weights=v,minlength=len(repos))
        d=g[draws].sum(axis=1)/counts[draws].sum(axis=1)
        changed=np.asarray([r['methods'][a]['choice']!=r['methods'][b]['choice'] for r in decisions])
        assert not np.any(v[~changed])
        diff_n=int(changed.sum());leave=(v.sum()-g)/(n-counts)
        result['contrasts'][a+'-'+b]=dict(delta=float(v.mean()),repo_cluster_ci=np.quantile(d,[.025,.975]).tolist(),
            wins=int((v>0).sum()),losses=int((v<0).sum()),ties=int((v==0).sum()),changed_choice=diff_n,
            changed_hits_first=int(av[changed].sum()),changed_hits_second=int(bv[changed].sum()),
            changed_delta=float(v[changed].mean()) if diff_n else None,
            repos_net_positive=int((g>0).sum()),repos_net_negative=int((g<0).sum()),repos_net_zero=int((g==0).sum()),
            equally_weighted_repo_delta=float(np.mean(g/counts)),leave_one_repo_out_range=[float(min(leave)),float(max(leave))])
    return result


def main():
    lock=load(HERE/'decision_lock.json')
    for name,h in lock['sha256'].items():
        assert digest((HERE/name).read_bytes())==h
    decisions=load(HERE/'decisions.json.gz')
    goldrows=load(WRITE/'gold.json.gz')
    gold={(ident('repo#'+r['repo']),r['issue']):set(r['keys']) for r in goldrows}
    assert set(gold)=={(r['repo'],r['issue']) for r in decisions} and len(decisions)==len(gold)==lock['n']
    scores=[]
    for r in decisions:
        true=gold[r['repo'],r['issue']];c=set(r['candidates'])
        assert all(m['choice'] in c for m in r['methods'].values())
        scores.append(dict(repo=r['repo'],issue=r['issue'],sequence=r['sequence'],prefix=r['prefix'],gold=sorted(true),
                           available=bool(c&true),hit={m:int(info['choice'] in true) for m,info in r['methods'].items()}))
    result=summarize(scores,decisions,lock['methods'])
    save(HERE/'scores.json.gz',scores);save(HERE/'results.json',result)
    save(HERE/'score_lock.json',dict(decision_sha256=digest((HERE/'decision_lock.json').read_bytes()),
         previous_gold_sha256=digest((WRITE/'gold.json.gz').read_bytes()),
         sha256={n:digest((HERE/n).read_bytes()) for n in ('scores.json.gz','results.json','grade_cues.py')}))
    print('Reachable',result['reachable'],'/',result['n'],'in',result['repos'],'repositories')
    print('Hits',[(m,r['hits']) for m,r in result['methods'].items()])
    for key in ('stable8-latest8','stable8-path','latest8-path','uniform8-path','full_latest-path','path-recency'):
        s=result['contrasts'][key];print(key,s['wins'],s['losses'],s['changed_choice'],round(s['delta'],4),[round(x,4) for x in s['repo_cluster_ci']])

if __name__=='__main__':main()

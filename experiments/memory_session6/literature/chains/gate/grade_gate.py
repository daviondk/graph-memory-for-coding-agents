"""Score locked retrievals from independent target headers and paired whole-repository resamples."""
from collections import Counter,defaultdict
from itertools import combinations
from pathlib import Path
import numpy as np
from gate import BASE,CUE,METHODS
from common import digest,load,save,ident


def summary(rows):
    eligible=[x for x in rows if x['eligible']]
    n=len(eligible);repos=sorted({x['repo'] for x in eligible});out=dict(frozen=len(rows),excluded=len(rows)-n,n=n,repos=len(repos))
    if not n:return out
    rid={v:i for i,v in enumerate(repos)};cluster=np.asarray([rid[r['repo']] for r in eligible])
    counts=np.bincount(cluster,minlength=len(repos));draw=np.random.default_rng(18112026).integers(len(repos),size=(10000,len(repos)))
    def contrast(rs,a,b,with_ci=False):
        av=np.asarray([r['hit'][a] for r in rs],dtype=int);bv=np.asarray([r['hit'][b] for r in rs],dtype=int);v=av-bv
        diff=np.asarray([r['methods'][a]['choice']!=r['methods'][b]['choice'] for r in rs])
        d=dict(n=len(rs),wins=int(sum(v>0)),losses=int(sum(v<0)),ties=int(sum(v==0)),changed=int(sum(diff)),delta=float(v.mean()) if len(rs) else None,
            changed_hits_a=int(av[diff].sum()) if len(rs) else 0,changed_hits_b=int(bv[diff].sum()) if len(rs) else 0)
        if with_ci:
            totals=np.bincount(cluster,weights=v,minlength=len(repos))
            boot=totals[draw].sum(axis=1)/counts[draw].sum(axis=1)
            d.update(repo_cluster_ci=np.quantile(boot,[.025,.975]).tolist(),repo_positive=int(sum(totals>0)),repo_negative=int(sum(totals<0)))
        return d
    out.update(reachable=sum(r['reachable'] for r in eligible),unique=sum(r['unique'] for r in eligible),
        candidate_counts=dict(Counter(str(len(r['candidates'])) for r in eligible)),history_lengths=dict(Counter(str(r['prefix']) for r in eligible)),
        shared_main_repo_cases=sum(r['shared_main_repo'] for r in eligible),
        shared_main_repos=len({r['repo'] for r in eligible if r['shared_main_repo']}),
        previously_in_main_history=sum(r['previously_in_main_history'] is True for r in eligible),
        discriminative_cues=sum(r['discriminates'] for r in eligible),
        different_tied_notes=sum((r['distinct_cues'] or 0)>1 for r in eligible),
        literal_overlap_cases=sum(r['any_literal_path_overlap'] for r in eligible),methods={},pairs={},strata={})
    for m in METHODS:
        out['methods'][m]=dict(hits=sum(r['hit'][m] for r in eligible),file_pointer_reads=n,
                extra_file_content_reads=0,cue_record_reads=sum(r['methods'][m]['records'] for r in eligible),
                cue_term_ids=sum(r['methods'][m]['ids'] for r in eligible),accessed_cases=sum(r['methods'][m]['records']>0 for r in eligible))
    for a,b in [('gate','path'),('gate','blind'),('gate','global'),('gate','recency'),('blind','path'),('global','path'),('path','recency')]:
        out['pairs'][a+'-'+b]=contrast(eligible,a,b,True)
    for key,fn in {'unique':lambda r:r['unique'],'positive_tie':lambda r:not r['unique'] and r['positive'],
                   'zero_tie':lambda r:not r['unique'] and not r['positive'],'zero_tie_ubiquitous':lambda r:not r['unique'] and not r['positive'] and r['any_literal_path_overlap'],
                   'zero_tie_no_literal':lambda r:not r['unique'] and not r['any_literal_path_overlap'],
                   'at_least_two_experiences':lambda r:r['prefix']>=2,'one_experience':lambda r:r['prefix']==1,
                   'repository_unseen_in_main':lambda r:not r['shared_main_repo']}.items():
        sub=[r for r in eligible if fn(r)]
        out['strata'][key]=contrast(sub,'gate','path')
    return out


def score():
    from sources import fetch,files,dedup,h
    lock=load(BASE/'decision_lock.json')
    for f,hval in lock['sha256'].items():assert digest((BASE/f).read_bytes())==hval
    dec=load(BASE/'decisions.json.gz')
    external=dedup(fetch('Related',['repo','instance_id','patch']))
    ekey={(ident('repo#'+repo),h(repo+'#issue#'+key)):(repo,v) for (repo,key),v in external.items()}
    chain=fetch('Chain',['continuous_id','repo','bug_fixes.list.element.swebench_instance_id','bug_fixes.list.element.patch'])
    ckey={h(r['continuous_id']):r for r in chain}
    old={(x['repo'],x['issue']):set(x['gold']) for x in load(CUE/'scores.json.gz')}
    out=[]
    for r in dec:
        z=(r['repo'],r['issue']);co=r['cohort']
        if co in ('chronological','linked'):
            repo,v=ekey[z];targets=set(files(repo,v['patch']))
        elif co=='second':
            src=ckey[r['sequence']];future=src['bug_fixes'][1];repo=src['repo']
            assert z==(ident('repo#'+repo),h(repo+'#issue#'+future['swebench_instance_id']))
            targets=set(files(repo,future['patch']))
        else:targets=old[z]
        hit={m:int(v['choice'] in targets) for m,v in r['methods'].items()}
        out.append({**r,'gold':sorted(targets),'eligible':bool(targets),'reachable':bool(set(r['candidates'])&targets),'hit':hit})
    save(BASE/'scores.json.gz',out)
    return out


def main():
    import sys
    data=load(BASE/'scores.json.gz') if '--offline' in sys.argv else score()
    report={cohort:summary([r for r in data if r['cohort']==cohort]) for cohort in ('chronological','linked','second','original')}
    save(BASE/'results.json',report)
    save(BASE/'score_lock.json',dict(decision_lock_sha256=digest((BASE/'decision_lock.json').read_bytes()),
        sha256={p:digest((BASE/p).read_bytes()) for p in ('grade_gate.py','scores.json.gz','results.json')}))
    for co,rep in report.items():
        p=rep['pairs']['gate-path'];b=rep['pairs']['gate-blind']
        print(co,'eligible',rep['n'],'/',rep['frozen'],'repos',rep['repos'],'reachable',rep['reachable'],'hits',{m:v['hits'] for m,v in rep['methods'].items()},'gate-path',p,'gate-blind',b)

if __name__=='__main__':main()

"""Strict confirmed-patch availability on the original shelves without refilling."""
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from gate import BASE,CUE,choose,METHODS
from common import digest,load,save
from grade_gate import summary
DATES=BASE.parent/'merge_times'

def parsed(s):
    return datetime.fromisoformat(s.replace('Z','+00:00')) if s else None

def freeze():
    verified=load(DATES/'verified_times.json');targets=load(DATES/'target_dates.json')
    features=[r for r in load(BASE/'features.json.gz') if r['cohort'] in ('chronological','linked')]
    rows=[];logs=[]
    for r in features:
        cutoff=parsed(targets.get(r['issue']));kept=[];status=[]
        for i,h in enumerate(r['history']):
            meta=verified.get(h['issue'],{});at=parsed(meta.get('merged_at'))
            why='unknown' if at is None or cutoff is None else ('available' if at<cutoff else 'too_late')
            status.append(dict(index=i,issue=h['issue'],status=why,merged_at=meta.get('merged_at'),target_cutoff=targets.get(r['issue'])))
            if why=='available':kept.append((at,h['issue'],h))
        merged=sorted(kept,key=lambda x:(x[0],x[1]))
        usable=any(x[2]['files'] for x in kept)
        audit=dict(cohort=r['cohort'],issue=r['issue'],repo=r['repo'],fully_confirmed=len(kept)==len(r['history']),
                   usable=usable,ordered_differently=[x[1] for x in merged]!=[x[1] for x in kept],status=status)
        logs.append(audit)
        if not usable:continue
        for order,hist in [('merged',merged),('original',kept)]:
            z=choose({**r,'history':[x[2] for x in hist],'prefix':len(hist)})
            rows.append({**z,'order':order,'fully_confirmed':audit['fully_confirmed']})
    save(BASE/'strict_decisions.json.gz',rows);save(BASE/'strict_links.json.gz',logs)
    save(BASE/'strict_decision_lock.json',dict(sha256={f:digest((BASE/f).read_bytes()) for f in ('STRICT_PROTOCOL.md','strict.py','strict_decisions.json.gz','strict_links.json.gz')},
        prior=digest((BASE/'decision_lock.json').read_bytes()),merger_source=digest((DATES/'verified_times.json').read_bytes()),target_dates=digest((DATES/'target_dates.json').read_bytes())))

def grade():
    lock=load(BASE/'strict_decision_lock.json')
    for f,v in lock['sha256'].items():assert digest((BASE/f).read_bytes())==v
    assert lock['merger_source']==digest((DATES/'verified_times.json').read_bytes())
    original={(x['cohort'],x['issue']):x for x in load(BASE/'scores.json.gz') if x['cohort'] in ('chronological','linked')}
    result={};out=[];inventory={}
    for r in load(BASE/'strict_decisions.json.gz'):
        old=original[r['cohort'],r['issue']]
        gold=old['gold'];hit={m:int(v['choice'] in gold) for m,v in r['methods'].items()}
        out.append({**r,'eligible':bool(gold),'gold':gold,'hit':hit,'reachable':bool(set(r['candidates'])&set(gold))})
    logs=load(BASE/'strict_links.json.gz')
    for c in ('chronological','linked'):
        group=[r for r in logs if r['cohort']==c and original[c,r['issue']]['eligible']]
        counter=Counter(link['status'] for r in group for link in r['status'])
        inventory[c]=dict(target_n=len(group),usable=sum(r['usable'] for r in group),fully_verified=sum(r['fully_confirmed'] for r in group),
                           new_order=sum(r['usable'] and r['ordered_differently'] for r in group),link_status=dict(counter),
                           historical_unique=len({x['issue'] for r in group for x in r['status']}),
                           all_with_unknown=sum(any(x['status']=='unknown' for x in r['status']) for r in group),
                           all_with_late=sum(any(x['status']=='too_late' for x in r['status']) for r in group))
        for order in ('merged','original'):
            rs=[r for r in out if r['cohort']==c and r['order']==order]
            by={name:summary([r for r in rs if cond(r)]) for name,cond in [('all',lambda r:True),('full',lambda r:r['fully_confirmed']),('partial',lambda r:not r['fully_confirmed'])]}
            result[c+'_'+order]=by
    save(BASE/'strict_scores.json.gz',out);save(BASE/'strict_results.json',{'inventory':inventory,'comparison':result})
    for c in ('chronological','linked'):
        s=result[c+'_merged']['all'];print(c,inventory[c],s['n'],{m:v['hits'] for m,v in s.get('methods',{}).items()},s.get('pairs',{}).get('gate-path'))

if __name__=='__main__':
    freeze();grade()

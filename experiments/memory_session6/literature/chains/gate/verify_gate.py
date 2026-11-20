"""Portable validation of target separation, gates, frozen SHA-256, extra reads and strict timestamps."""
from collections import Counter
from datetime import datetime
import math
from gate import BASE,CUE,choose,METHODS
from common import digest,load

def parse(s):return datetime.fromisoformat(s.replace('Z','+00:00'))

def check_result(rs,result):
    good=[r for r in rs if r['eligible']]
    assert len(rs)==result['frozen'] and len(good)==result['n']
    if not good:return
    assert len({r['repo'] for r in good})==result['repos']
    assert sum(r['reachable'] for r in good)==result['reachable']
    for r in good:
        for m,t in r['methods'].items():
            assert t['choice'] in r['candidates'] and int(t['choice'] in r['gold'])==r['hit'][m]
        a,b=r['methods']['gate'],r['methods']['blind']
        assert a['records']==b['records'] and a['ids']==b['ids'] and a['choice'] in r['top'] and b['choice'] in r['top']
        if r['unique']:assert a['choice']==b['choice']==r['methods']['path']['choice'] and a['records']==a['ids']==0
        else:assert a['records']==len(r['top'])
    for m,v in result['methods'].items():
        assert sum(r['hit'][m] for r in good)==v['hits'] and v['file_pointer_reads']==len(good)
        assert sum(r['methods'][m]['records'] for r in good)==v['cue_record_reads']
        assert sum(r['methods'][m]['ids'] for r in good)==v['cue_term_ids']
    for methods,v in result['pairs'].items():
        a,b=methods.split('-');delta=[r['hit'][a]-r['hit'][b] for r in good]
        assert v['wins']==delta.count(1) and v['losses']==delta.count(-1) and math.isclose(v['delta'],sum(delta)/len(delta),abs_tol=1e-13)
        assert v['changed']==sum(r['methods'][a]['choice']!=r['methods'][b]['choice'] for r in good)

def main():
    for n in ('decision_lock.json','score_lock.json','strict_decision_lock.json','final_lock.json'):
        lock=load(BASE/n)
        for f,h in lock['sha256'].items():assert digest((BASE/f).read_bytes())==h
    features=load(BASE/'features.json.gz');dec=load(BASE/'decisions.json.gz');assert [choose(r) for r in features]==dec
    cohorts={c:{r['issue'] for r in features if r['cohort']==c} for c in ('original','second','chronological','linked')}
    assert not cohorts['original']&(cohorts['second']|cohorts['chronological']|cohorts['linked'])
    assert not cohorts['second']&(cohorts['chronological']|cohorts['linked'])
    aliases={c:{k for r in features if r['cohort']==c for k in r['aliases'].values()} for c in ('second','chronological','linked')}
    assert not aliases['second']&(aliases['chronological']|aliases['linked'])
    scores=load(BASE/'scores.json.gz');results=load(BASE/'results.json')
    for co,res in results.items():check_result([r for r in scores if r['cohort']==co],res)
    all_times=load(BASE.parent/'merge_times'/'verified_times.json');target_dates=load(BASE/'strict_target_dates.json')
    other=BASE.parent/'merge_times'/'target_dates_first.json'
    if other.exists():assert load(other)==target_dates
    slock=load(BASE/'strict_decision_lock.json')
    assert digest((BASE.parent/'merge_times'/'verified_times.json').read_bytes())==slock['merger_source']
    assert digest((BASE/'strict_target_dates.json').read_bytes())==slock['target_dates']
    sf=load(BASE/'strict_decisions.json.gz');orig={(x['cohort'],x['issue']):x for x in features}
    sid={(r['cohort'],r['issue'],r['order']):r for r in sf}
    for log in load(BASE/'strict_links.json.gz'):
        ref=orig[log['cohort'],log['issue']];cut=parse(target_dates[ref['issue']]);accepted=[]
        for old,v in zip(ref['history'],log['status'],strict=True):
            assert old['issue']==v['issue'];at=all_times[old['issue']].get('merged_at');assert at==v['merged_at']
            status='unknown' if not at else ('available' if parse(at)<cut else 'too_late')
            assert status==v['status']
            if status=='available':accepted.append((parse(at),old['issue'],old))
        valid=any(x[2]['files'] for x in accepted);assert valid==log['usable']
        for order,observations in [('merged',sorted(accepted,key=lambda x:(x[0],x[1]))),('original',accepted)]:
            key=ref['cohort'],ref['issue'],order
            if not valid:assert key not in sid;continue
            test=choose({**ref,'history':[v[2] for v in observations],'prefix':len(observations)})
            assert {**test,'order':order,'fully_confirmed':len(accepted)==len(ref['history'])}==sid[key]
    ss=load(BASE/'strict_scores.json.gz');sr=load(BASE/'strict_results.json')
    for key,groups in sr['comparison'].items():
        co,order=key.split('_');rs=[r for r in ss if r['cohort']==co and r['order']==order]
        for subset,res in groups.items():
            use=[r for r in rs if subset=='all' or (r['fully_confirmed'] if subset=='full' else not r['fully_confirmed'])]
            check_result(use,res)
    print('PASS: four cohort gates, all individual outcomes, matched cue access, verified PR times, both strict replays and all paired counts.')
if __name__=='__main__':main()

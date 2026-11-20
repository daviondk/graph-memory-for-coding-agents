"""Verify local locks, opaque features, admissions, all 2,244 choices and paired hits; standard Python."""
from collections import Counter
import math
import re
from common import HERE,WRITE,digest,ident,load
from predict import predict


def main():
    dec=load(HERE/'decision_lock.json');graded=load(HERE/'score_lock.json');results=load(HERE/'results.json')
    for lock in (dec,graded):
        for n,h in lock['sha256'].items():assert digest((HERE/n).read_bytes())==h,n
    assert graded['decision_sha256']==digest((HERE/'decision_lock.json').read_bytes())
    assert dec['historical_writer_sha256']==digest((WRITE/'retain.py').read_bytes())
    decisions=load(HERE/'decisions.json.gz');features=load(HERE/'features.json.gz');scores=load(HERE/'scores.json.gz')
    assert [predict(r) for r in features]==decisions
    ids={};tok=re.compile(r'[a-f0-9]{24}')
    def anon(vals):assert all(tok.fullmatch(w) for w in vals)
    for e,r,s in zip(features,decisions,scores,strict=True):
        k=tuple(r[x] for x in ('repo','issue','sequence','prefix'))
        assert k==tuple(s[x] for x in ('repo','issue','sequence','prefix')) and k not in ids
        ids[k]=r;anon(k[:3]);anon(e['query']);anon(r['candidates']);anon(s['gold'])
        for step in e['history']:
            anon(step['terms']);anon(step['files'])
            for f in step['files'].values():anon([f['folder'],*f['words']])
        assert 1<=len(r['candidates'])<=8 and e['expected_cache']==r['candidates']
        assert bool(set(r['candidates'])&set(s['gold']))==s['available']
        for m,entry in r['methods'].items():
            assert entry['choice'] in r['candidates'] and int(entry['choice'] in s['gold'])==s['hit'][m]
        fills=[r['methods'][m]['cue_ids'] for m in ('stable8','latest8','uniform8')]
        assert len(set(fills))==1 and fills[0]<=8*len(r['candidates'])
    orig=load(WRITE/'decisions.json.gz')
    assert { (ident('repo#'+r['repo']),r['issue'],r['sequence'],r['previous_tasks']) for r in orig}==set(ids)
    assert len(ids)==dec['n']==len(scores)==results['n']==374 and len({k[0] for k in ids})==77
    assert sum(s['available'] for s in scores)==results['reachable']
    for m,v in results['methods'].items():
        assert v['reads']==len(scores) and v['hits']==sum(s['hit'][m] for s in scores)
        assert v['cue_ids_total']==sum(r['methods'][m]['cue_ids'] for r in decisions)
    for key,v in results['contrasts'].items():
        a,b=key.split('-');d=[s['hit'][a]-s['hit'][b] for s in scores]
        assert v['wins']==d.count(1) and v['losses']==d.count(-1) and math.isclose(v['delta'],sum(d)/len(d),abs_tol=1e-12)
        assert v['changed_choice']==sum(r['methods'][a]['choice']!=r['methods'][b]['choice'] for r in decisions)
    print('PASS: 374 identical historical prefixes, six locked decisions each, opaque words, true read budgets, 15 contrasts.')

if __name__=='__main__':main()

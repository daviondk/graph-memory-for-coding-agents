"""Recompute results from frozen solver calls and separately executed public fixtures (stdlib only)."""
import csv
import math
import random
from collections import Counter
from common import *

def counts(answers,keys):
    by_key={r['key']:r['ok'] for r in answers}
    assert len(by_key)==len(answers) and keys<=by_key.keys()
    return sum(by_key[k] for k in keys)

def contrast(rows,a,b):
    differences=[int(r['future_all_'+a])-int(r['future_all_'+b]) for r in rows]
    wins=differences.count(1); losses=differences.count(-1); n=wins+losses
    if not differences:return {}
    rng=random.Random(17112026)
    estimates=sorted(sum(rng.choices(differences,k=len(rows)))/len(rows) for _ in range(10000))
    return {'programs':len(rows),'wins':wins,'losses':losses,'ties':len(rows)-n,'delta':sum(differences)/len(rows),
            'paired_program_bootstrap_95':[estimates[249],estimates[9749]],
            'exact_discordant_sign_p':min(1,2*sum(math.comb(n,i) for i in range(min(wins,losses)+1))/2**n)}

def main():
    for n in ('input_lock','solver_lock','output_lock'):
        locked=read(n+'.json')['files'];assert locked==freeze(locked)
    ds=read('decisions.json'); index={(d['name'],d['arm']):d for d in ds}
    rows=[]; roster=read('roster.json')
    for r in roster:
        if not r['eligible']:continue
        name=r['name'];f=read('fixtures/'+name+'.json'); keys={c['key'] for c in f['cases']}
        future={c['key'] for c in f['cases'] if c['part']=='future'}
        before=keys-future;original=f['original']; assert counts(f['correct_controls'],keys)==len(keys)
        row={'program':name,'future_cases':len(future),'all_cases':len(keys),
             'failed_in_history':counts(original,before)<len(before),'future_detects_bug':counts(original,future)<len(future),'doctest_present':r['example_in_source']}
        for a in ['original']+ARMS:
            if a=='original':res=original
            else:
                d=index[name,a];res=read('grades/'+name+'-'+sha(d['candidate'])+'.json')
                call=read('calls/'+d['key']+'.json')
                assert d['key']==sha(obj(call['payload'])) and d['response_id']==call['response']['id']
                row['memory_chars_'+a]=len(f['memory'][a])
                for m in ('prompt_tokens','completion_tokens'):row[m+'_'+a]=d['usage'][m]
            assert len(res)==len(keys)
            row['future_ok_'+a]=counts(res,future);row['future_all_'+a]=counts(res,future)==len(future)
            row['all_pass_'+a]=counts(res,keys)==len(keys)
        rows.append(row)
    with (ROOT/'per_program.csv').open('w',encoding='utf8',newline='') as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    def group(subset):
        return {'N':len(subset),'arms':{a:{'future_all':sum(r['future_all_'+a] for r in subset),
                'full_suite':sum(r['all_pass_'+a] for r in subset),'passed_future_cases':sum(r['future_ok_'+a] for r in subset),
                'future_cases':sum(r['future_cases'] for r in subset)} for a in ['original']+ARMS},
                'witness_vs':{b:contrast(subset,'witness',b) for b in ('recent','empty','full')}}
    calls={d['key']:d for d in ds}
    save('results.json',{'all':group(rows),'observed_failure':group([r for r in rows if r['failed_in_history']]),
        'future_exposes_bug':group([r for r in rows if r['future_detects_bug']]),
        'cost_by_arm':{a:{m:sum(r[m+'_'+a] for r in rows) for m in ('prompt_tokens','completion_tokens','memory_chars')} for a in ARMS},
        'actual_native_calls':len(calls),'assignments':len(ds),'actual_usage':{m:sum(d['usage'][m] for d in calls.values()) for m in ('prompt_tokens','completion_tokens')},
        'length_finishes_unique':sum(d['length_finish'] for d in calls.values()),'exclusions':[r for r in roster if not r['eligible']],
        'registered_contrasts':'exploratory unadjusted p-values, not independent replications; bootstrap resamples programs, degenerate for identical results'})
    print(json.dumps(read('results.json')['all'],indent=1))
if __name__=='__main__':main()

"""Re-fit all folds and compare every out-of-project selection with its sealed decision."""
from predict import *
from score import compute,key,read
if __name__=='__main__':
    design=csvrows(ART/'assignments.csv')
    outcomes={r['run_id']:int(r['official_known']=='1' and r['official_resolved']=='1') for r in csvrows(ART/'arm_outcomes.csv')}
    actual={key(p):p for p in read('decisions.json')}
    for group in read('folds.json'):
        training=[r for r in design if repo(r)!=group]
        train_ids={r[a] for r in training for a in ARMS}
        restricted={k:outcomes[k] for k in train_ids}
        model=fit(training,restricted)
        for r in design:
            if repo(r)==group:
                p=actual[key(r)]
                assert group==p['group'] and all(r[a] not in restricted for a in ARMS)
                assert predict(model,r)==tuple(p[c] for c in ['constant','recipient','candidate'])
    assert compute()==read('results.json')
    print('All 11 disjoint project folds and 1,530 selections verified.')


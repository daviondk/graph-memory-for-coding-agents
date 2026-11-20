"""Evaluate frozen held-out decisions, preserving unknown checks and paired costs."""
from collections import Counter,defaultdict
import hashlib
import json
import random
from statistics import mean
from predict import ARMS,ART,ROOT,csvrows,dump
def read(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def key(r):return tuple(r[k] for k in ['instance','pred','succ','checkpoint'])
def compare(steps,decision,baseline):
    wins=losses=0;known_n=known_diff=0
    delta=[];cluster=defaultdict(list)
    for p,answers in steps:
        a,b=answers[p.get(decision,decision)],answers[p.get(baseline,baseline)]
        good=lambda u:int(u['official_known']=='1' and u['official_resolved']=='1')
        d=good(a)-good(b); wins+=d==1;losses+=d==-1;cluster[p['group']].append(d)
        if a['official_known']==b['official_known']=='1':known_n+=1;known_diff+=d
        if a['prompt_tokens'] and b['prompt_tokens']:delta.append(int(a['prompt_tokens'])-int(b['prompt_tokens']))
    groups=[(sum(ds),len(ds)) for ds in cluster.values()]
    rr=random.Random(20261116);bs=[]
    for _ in range(10000):
        draw=rr.choices(groups,k=len(groups));bs.append(100*sum(s for s,n in draw)/sum(n for s,n in draw))
    bs.sort()
    return {'n':len(steps),'wins':wins,'losses':losses,'delta_pp':100*(wins-losses)/len(steps),'repo_conditional_ci95_pp':[bs[249],bs[9749]],'known_both':known_n,'known_net':known_diff,'mean_delta_tokens':mean(delta),'token_pairs':len(delta)}
def compute():
    for n,h in read('lock.json').items():
        f=ROOT/n if (ROOT/n).is_file() else ART/n
        assert hashlib.sha256(f.read_bytes()).hexdigest()==h
    design={key(x):x for x in csvrows(ART/'assignments.csv')}
    outcomes={r['run_id']:r for r in csvrows(ART/'arm_outcomes.csv')}
    steps=[(p,{a:outcomes[design[key(p)][a]] for a in ARMS}) for p in read('decisions.json')]
    assert len(steps)==len(design)==len({key(p) for p,y in steps})==1530
    out={'issues':len({p['instance'] for p,y in steps}),'repositories':len({p['group'] for p,y in steps}),'policies':{},'comparisons':{}}
    for k in ARMS+['constant','recipient','candidate']:
        vals=[y[p.get(k,k)] for p,y in steps]
        n=sum(r['official_known']=='1' and r['official_resolved']=='1' for r in vals)
        out['policies'][k]={'solved':n,'n':len(vals),'known':sum(r['official_known']=='1' for r in vals),'formats':dict(Counter(p.get(k,k) for p,_ in steps))}
    for b in ['raw_trace','structured_notes','constant','recipient']:out['comparisons'][b]=compare(steps,'candidate',b)
    return out
if __name__=='__main__':
    results=compute();dump('results.json',results);print(results)


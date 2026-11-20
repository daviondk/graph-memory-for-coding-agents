"""Check candidate cohort geometry and identical-message cancellations, without reference continuations."""
from collections import Counter
from independent import INPUT,read,save
pop=read(INPUT/'E_population.json.gz');d=read(INPUT/'D_assignment.json');e=read(INPUT/'E_assignment.json')
p={r['id']:r for r in pop}; assert len(p)==len(pop)
elig=[r for r in pop if r['eligible']];dyn=[r for r in elig if r['changed']]
assert {r['id'] for r in dyn}==set(e)
for row in elig:assert row['changed']==(row['hashes'][0]!=row['hashes'][1])
for uid,b in e.items():
    assert b['bridge']!=b['order']
    if uid in d:assert all(d[uid][k]==v for k,v in b.items())
for uid,v in d.items():
    assert p[uid]['eligible']
    assert p[uid]['changed']==(v['bridge']!=v['order'])
freq=Counter(r['repo'] for r in dyn); totalfreq=Counter(r['repo'] for r in elig)
save('roster_only.json',{'nD':len(d),'nE':len(elig),'e_changed':len(dyn),'e_null_equal_hash':len(elig)-len(dyn),'e_reranked':sum(r.get('reranked',False) for r in elig),'new_projects_questions':sum(not r['known'] for r in elig),'new_projects_changed':sum(not r['known'] for r in dyn),'eligible_projects':len(totalfreq),'changed_projects':len(freq),'per_repo_changes':freq,'overlap_D_Eall':len(set(d)&set(p)),'overlap_D_Echanged':len(set(d)&set(e)),'one_question_max_global_pp':100/len(elig),'global_em_bound_pp':100*len(dyn)/len(elig)})


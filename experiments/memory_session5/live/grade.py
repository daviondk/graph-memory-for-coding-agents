"""Score generated physical edits with the published tests, after both prediction locks."""
import collections,concurrent.futures,math,random,statistics
from common import *
from memory import ARMS,apply_edit
import ast

def ci(diffs):
    rng=random.Random(17112026);n=len(diffs)
    if not n:return None
    vals=sorted(sum(rng.choices(diffs,k=n))/n for _ in range(10000))
    return [vals[249],vals[9749]]
def paired(vals,base):
    d=[x-y for x,y in zip(vals,base)];w=sum(i>0 for i in d);l=sum(i<0 for i in d);n=w+l
    return {'n':len(d),'mean_delta':sum(d)/len(d),'ci95':ci(d),'wins':w,'losses':l,'ties':len(d)-n,
            'exact_p': min(1,2*sum(math.comb(n,i) for i in range(min(w,l)+1))/2**n) if n else 1}
def bundle_gate(source,focus,center):
    candidates=[n for n in ast.walk(ast.parse(source)) if isinstance(n,(ast.If,ast.While,ast.For)) and n.lineno<focus<=n.end_lineno]
    if not candidates:return False
    nearest=max(candidates,key=lambda n:n.lineno)
    return focus-nearest.lineno>=3 and nearest.lineno not in {int(x.split('|',1)[0]) for x in center.splitlines() if '|' in x}
def outcome(cohort,task,r,arm):
    folder=ROOT/cohort;q=slug(task)
    source=src(r)
    if arm in ('canonical','buggy'):
        text=source if arm=='buggy' else r['declaration']+r['canonical_solution'];policy='control';calls=[];reread=False
    else:
        d=read(folder.relative_to(ROOT)/'decisions'/(q+'-'+arm+'.json'))
        text,policy=apply_edit(source,d['answer']);calls=d['calls'];reread=d['reread']
    path=folder/'artifacts'/q/arm/'solution.py'
    path.parent.mkdir(exist_ok=True,parents=True)
    if text is not None:
        path.write_bytes(text.encode())
        assert path.read_bytes()==text.encode()
        evaluated=run_suite(path,r['entry_point'],r['test'])
    else:evaluated={'status':'invalid_edit'}
    usage=collections.Counter()
    for k in calls:
        package=read(folder.relative_to(ROOT)/'calls'/(k+'.json.gz'));u=package['response']['usage']
        usage.update({k:u[k] for k in ('prompt_tokens','completion_tokens','total_tokens')})
    return {'id':task,'arm':arm,'action':policy,'evaluated':evaluated,'hit':int(evaluated['status']=='pass' and policy in ('applied','control')),
            'reread':reread,'first_hit':int(evaluated['status']=='pass' and not reread and policy in ('applied','control')),
            'patch_sha':digest(text) if text is not None else None,'usage':dict(usage),'applied':int(policy=='applied')}
def summary(cohort,ids,rows,rs):
    d={(r['id'],r['arm']):r for r in rows};arms=list(ARMS)
    params={};picked=[];packets=collections.defaultdict(list)
    for i in ids:
        pref=read((ROOT/cohort/'prefix'/(slug(i)+'.json')).relative_to(ROOT));gate=bundle_gate(src(rs[i]),pref['focus'],pref['notes']['center'])
        d[i,'gate']=d[i,'bundle' if gate else 'center'];picked.append(gate)
        for a in arms:packets[a].append(pref['exposed_tokens'][a])
    def report(sub):
        stats={}
        for a in arms+['gate','buggy','canonical']:
            obs=[d[i,a] for i in sub];stats[a]={'n':len(obs),'solves':sum(x['hit'] for x in obs),'first_solves':sum(x['first_hit'] for x in obs),
                'rereads':sum(x['reread'] for x in obs),'applied':sum(x['applied'] for x in obs),
                'input_tokens':sum(x['usage'].get('prompt_tokens',0) for x in obs),'output_tokens':sum(x['usage'].get('completion_tokens',0) for x in obs),
                'status':dict(collections.Counter(x['evaluated']['status'] for x in obs))}
        contrasts={}
        for a,b in [('bundle','center'),('bundle','recent'),('bundle','none'),('bundle','full'),('gate','center'),('gate','bundle'),('center','none')]:
            for endpoint in ('hit','first_hit','reread'):
                contrasts[a+'-'+b+'-'+endpoint]=paired([int(d[i,a][endpoint]) for i in sub],[int(d[i,b][endpoint]) for i in sub])
        return {'rows':stats,'paired':contrasts}
    eligible=[i for i in ids if d[i,'canonical']['hit'] and not d[i,'buggy']['hit']]
    return {'all':report(ids),'valid_sensitivity':report(eligible) if eligible else None,'n_valid':len(eligible),'gate_used':sum(picked),
            'memory_token_avg':{a:statistics.mean(v) for a,v in packets.items()},'task_ids':ids,
            'non_discriminating':{i:[d[i,'buggy']['evaluated'],d[i,'canonical']['evaluated']] for i in ids if i not in eligible}}
def main():
    for sub in ('','transfer'):
        lock=read((ROOT/sub/'prediction_lock.json').relative_to(ROOT))
        assert all(digest((ROOT/sub/f).read_bytes())==h for f,h in lock.items())
    rs=corpus()
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        for sub in ('','transfer'):
            ids=read((ROOT/sub/'roster.json').relative_to(ROOT))['ids']
            todo=[(sub,i,rs[i],a) for i in ids for a in (*ARMS,'buggy','canonical')]
            rows=list(pool.map(lambda args:outcome(*args),todo))
            save((ROOT/sub/'scores.json.gz').relative_to(ROOT),rows)
            report=summary(sub,ids,rows,rs);save((ROOT/sub/'results.json').relative_to(ROOT),report)
            print(sub or 'primary',report['all']['rows'],flush=True)
if __name__=='__main__':main()

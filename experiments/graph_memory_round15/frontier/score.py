"""Compute bounded-budget outcomes, opportunity costs and task-cluster intervals."""
import statistics
import numpy as np
from frontier import *
METHODS=('view_graph','flat_recent','bm25_all','flat_union','typed_union','shuffled_union','alternating_union','random_all')
K=(1,3,6)
ENDS=('patch_strict','patch_official','next')
PAIR=('view_graph','flat_union','shuffled_union','alternating_union','bm25_all','flat_recent','random_all')
def audit_source(est):
    assert all(h((D/n).read_bytes())==d for n,d in read(D/'forecast.lock.json').items())
    assert est['forecast_lock']==h((D/'forecast.lock.json').read_bytes())
    assert all(h((D/n).read_bytes())==d for n,d in est['files'].items())
def consume(r,p,t):
    goal=set(t);old=set(r['viewed']);new=set(r['frontier'])
    assert not old&new
    ranking=p['ranks']
    rr={m:next((i for i,x in enumerate(xs,1) if x in goal),0) for m,xs in ranking.items()}
    return {'id':r['id'],'iid':r['iid'],'repo':r['repo'],'ranks':rr,'old_hit':bool(goal&old),'all_hit':bool(goal&(old|new)),
            'frontier_hit':bool(goal&new),'new_gold_paths':sorted(goal&new),'grounded_member':r['grounded_member'],'targets':sorted(goal),
            'new_read':{m:[sum(x in new for x in xs[:k]) for k in K] for m,xs in ranking.items()}}
def measure(n):return (int(n==1),int(0<n<=3),int(0<n<=6),1/n if n else 0.)
def pair(rows):
    ids=sorted({r['iid'] for r in rows});ix={d:i for i,d in enumerate(ids)}
    count=np.bincount([ix[r['iid']] for r in rows]);rng=np.random.default_rng(301754)
    counts=rng.multinomial(len(ids),[1/len(ids)]*len(ids),size=5000);denom=(counts@count)[:,None];out={}
    for m in PAIR:
        vals=np.array([[a-b for a,b in zip(measure(r['ranks']['typed_union']),measure(r['ranks'][m]))] for r in rows])
        per=np.zeros((len(ids),4))
        for r,x in zip(rows,vals):per[ix[r['iid']]]+=x
        bp=(counts@per)/denom
        out[m]={x:{'delta':float(vals[:,j].mean()),'wins':int((vals[:,j]>0).sum()),'losses':int((vals[:,j]<0).sum()),
               'ci95':np.quantile(bp[:,j],[.025,.975]).tolist()} for j,x in enumerate(('h1','h3','h6','mrr'))}
    return out

def main():
    audit_source(read(D/'outcome.lock.json'))
    inp=read(D/'frontier_inputs.json.gz');pred=read(D/'forecasts.json.gz');labels=read(D/'outcomes.json.gz')
    native={r['id']:[c['path'] for c in r['menu']] for r in read(G/'cases.gz')}
    ret={};detail={};allpairs={};mem={}
    for n,L in inp.items():
        rs=collections.defaultdict(list);ps={p['id']:p for p in pred[n]};targets={p['id']:p for p in labels[n]}
        for r in L:
            for ep in ENDS:
                if targets[r['id']][ep]:
                    one=consume(r,ps[r['id']],targets[r['id']][ep])
                    if r['grounded_member']:one['r14_original_hit']=bool(set(native[r['id']])&set(one['targets']))
                    rs[ep].append(one)
        variants=[(n,rs)]
        if n=='grounded_all':
            gu={r['iid'] for r in L if r['grounded_member']}
            variants.extend([('grounded_original',{ep:[r for r in ss if r['grounded_member']] for ep,ss in rs.items()}),
                       ('grounded_other_tasks',{ep:[r for r in ss if r['iid'] not in gu] for ep,ss in rs.items()})])
        for name,grp in variants:
            ret[name]={};detail[name]=grp;allpairs[name]={}
            for ep,rows in grp.items():
                if not rows:continue
                m={}
                for method in METHODS:
                    vals=[r['ranks'][method] for r in rows]
                    m[method]={f'h{k}':sum(0<v<=k for v in vals) for k in K}
                    m[method].update(mrr=sum(1/v for v in vals if v)/len(vals),
                                     avg_new_slots=[statistics.mean(r['new_read'][method][j] for r in rows) for j in range(3)])
                summ={'n':len(rows),'tasks':len({r['iid'] for r in rows}),'old_oracle':sum(r['old_hit'] for r in rows),
                             'union_oracle':sum(r['all_hit'] for r in rows),'new_only_oracle':sum(r['all_hit'] and not r['old_hit'] for r in rows),
                             'new_any_oracle':sum(r['frontier_hit'] for r in rows),'methods':m}
                if name=='grounded_original':
                    summ['r14_menu_oracle']=sum(r['r14_original_hit'] for r in rows)
                    summ['r14_missing_now_in_old_full']=sum(not r['r14_original_hit'] and r['old_hit'] for r in rows)
                    summ['r14_missing_now_new_only']=sum(not r['r14_original_hit'] and r['all_hit'] and not r['old_hit'] for r in rows)
                ret[name][ep]=summ;allpairs[name][ep]=pair(rows)
        cues=collections.Counter(t for r in L for o in r['frontier'].values() for t in o['sources'])
        bytes_=[r['frontier_bytes'] for r in L];opened=[r['opened_bytes'] for r in L]
        mem[n]={'anchors':len(L),'mentions':sum(len(r['frontier']) for r in L),'corroborated_slots':sum(sum(p['scores']['corroborated'].values()) for p in ps.values()),
                'corroborated_anchors':sum(any(p['scores']['corroborated'].values()) for p in ps.values()),'source_types':cues,
                'frontier_json_bytes':{'median':statistics.median(bytes_),'p90':float(np.quantile(bytes_,.9)),'max':max(bytes_)},
                'opened_guard_json_bytes':{'median':statistics.median(opened),'p90':float(np.quantile(opened,.9)),'max':max(opened)}}
    save('results.json',ret);save('paired.json',allpairs);save('evaluation_rows.json.gz',detail);save('memory_cost.json',mem)
    for n,x in ret.items():
        for e in ('patch_strict','patch_official','next'):
            if e in x:
                y=x[e];print(n,e,y['n'],y['old_oracle'],y['union_oracle'],{m:y['methods'][m]['h6'] for m in METHODS})
if __name__=='__main__':main()

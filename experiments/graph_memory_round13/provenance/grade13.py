"""Load independent Git outcomes after verifying forecast seal; compute per-task uncertainty."""
from collections import Counter,defaultdict
import hashlib,math,statistics
import numpy as np
from common13 import D,R12,read,dump,sha,digest,obs
from engine import scan
def distribution(y,mask,ids,boot,seed):
    n=len(y);tasks=sorted(set(ids));by=[np.where(ids==i)[0] for i in tasks]
    pop=np.array([len(v) for v in by]);k=np.array([mask[v].sum() for v in by]);bad=np.array([y[v].sum() for v in by])
    err=np.array([(y[v]&mask[v]).sum() for v in by]);ex=k*bad/pop
    draws=np.random.default_rng(seed);perm=np.zeros(4096,dtype=int)
    for a,b,c in zip(bad,pop,k):perm+=draws.hypergeometric(a,b-a,c,size=len(perm))
    B=k[boot].sum(1);E=err[boot].sum(1);X=ex[boot].sum(1);P=pop[boot].sum(1)
    def ci(a):return [float(v) for v in np.quantile(a,[.025,.975])] if len(a) else [None,None]
    reuse=int(k.sum());wrong=int(err.sum())
    return dict(n=n,reused=reuse,rescans=n-reuse,unsafe_total=int(y.sum()),unsafe_reused=wrong,unsafe_caught=int(y.sum())-wrong,
                coverage=reuse/n,coverage_ci=ci(B/P),risk=wrong/reuse if reuse else None,risk_ci=ci(E[B>0]/B[B>0]),
                expected_random_errors=reuse*float(y.mean()),expected_task_matched_errors=float(ex.sum()),random_matched_error_range=ci(perm),
                task_matched_risk_delta=(wrong-ex.sum())/reuse if reuse else None,task_matched_delta_ci=ci((E[B>0]-X[B>0])/B[B>0]),
                task_matched_one_sided_p=(1+int((perm<=wrong).sum()))/4097 if reuse else None,
                informative_tasks=int(sum((k>0)&(k<pop)&(bad>0)&(bad<pop))),bootstrap_nonzero=int(sum(B>0)))
def resources(row,arm):
    evs=row['evidence'];bids=set()
    if arm in ('trust','always_scan','cwd','pwd','prefix_red_flag','hash'):return bids
    if arm=='path_exists':return {row['tree']}
    if arm=='directory':return {row['tree']} if any(x['kind']=='ls' for x in evs) else set()
    if arm=='last_r12':
        work=[]
        for x in reversed(evs):
            work.append(x)
            if x['matched']>=(3 if x['kind']=='ls' else 2):break
        evs=work
    else:
        if arm not in ('rank',):evs=[x for x in evs if x['kind']=='content']
        if arm in ['scope_content','fresh_scope_strict','two_scope_files','strict_conflict_veto','verified_red_flag']:evs=[x for x in evs if x['scope']]
        if arm in ['fresh_content','fresh_scope_strict']:evs=[x for x in evs if x['age']<=5]
        if arm=='verified_red_flag':evs=[x for x in evs if x['prior_positive']]
    if evs:bids.add(row['tree'])
    return bids|{x['blob'] for x in evs if x['blob']}
def main():
    seal=read(D/'forecast_lock.json')
    assert digest(D/'features.json.gz')==seal['features'] and all(digest(D/k)==v for k,v in seal['code'].items())
    rows=read(D/'features.json.gz');oracle={obs(z):z for z in read(R12/'outcomes.json.gz')};blobs=read(R12/'independent_blob_checks.json.gz')
    assert {r['id'] for r in rows}==set(oracle)
    direct={};ops=read(D/'operations.json')
    for row in rows:
        rr=oracle[row['id']];assert row['rev']==rr['old']
        if not rr.get('oracle'):continue
        y=rr['oracle']['old']['hit'];times=[]
        for _ in range(3):
            value,ns,out,_=scan(row['repo'],row['rev'],rr['key'],rr['old_scope'])
            assert value==y and out==0;times.append(ns)
        b=blobs[row['id']]['old'];assert b['agrees'] and bool(b['hit_files'])==y
        direct[row['id']]=dict(hit=y,ns=times,median_ns=statistics.median(times),eligible_blob_bytes=b['bytes'],eligible_files=b['files'],scope_kind=rr['old_scope'])
    dump(D/'direct_receipts.json',direct);selected=[r for r in rows if r['id'] in direct];n=len(selected)
    y=np.array([bool(direct[r['id']]['hit']) for r in selected]);ids=np.array([r['iid'] for r in selected]);nt=len(set(ids));rng=np.random.default_rng(13027);boot=rng.integers(0,nt,(10000,nt))
    policies=sorted(selected[0]['trust']);table={};decisions=[]
    def evaluate(a,mask):
        cell=distribution(y,mask,ids,boot,13027)
        receipts=[resources(r,a) for r in selected]
        ops_per_task={(r['iid'],op) for r,used in zip(selected,receipts) for op in used}
        abstain=[direct[r['id']] for r,take in zip(selected,mask) if not take]
        cell.update(prefix_feature_cold_ops=sum(map(len,receipts)),prefix_feature_task_cached_ops=len(ops_per_task),prefix_feature_cold_bytes=sum(ops[o]['bytes'] for rs in receipts for o in rs),prefix_feature_cached_bytes=sum(ops[o]['bytes'] for i,o in ops_per_task),prefix_feature_cached_ms=sum(ops[o]['ns'] for i,o in ops_per_task)/1e6,paid_rescan_ms=sum(r['median_ns'] for r in abstain)/1e6,eligible_rescan_blob_bytes=sum(r['eligible_blob_bytes'] for r in abstain))
        return cell
    for a in policies:
        mask=np.array([r['trust'][a] for r in selected])
        table[a]=evaluate(a,mask)
    ranked=sorted(range(n),key=lambda i:(tuple(-v for v in selected[i]['score']),sha(selected[i]['id'].encode())))
    baseline=sorted(range(n),key=lambda i:sha(selected[i]['id'].encode()))
    curves={}
    for a,order in [('rank',ranked),('hash',baseline)]:
        curve={};cumulative=np.cumsum(y[np.array(order)]);curve['aurc']=float(np.mean(cumulative/np.arange(1,n+1)))
        for frac in [.1,.25,.5,.75,.9,1]:
            k=round(n*frac);mask=np.zeros(n,dtype=bool);mask[order[:k]]=True;curve[str(frac)]=evaluate(a,mask)
        curves[a]=curve
    truth=[dict(id=r['id'],iid=r['iid'],repo=r['repo'],hit=bool(v),forecasts=r['trust'],score=r['score'],order=ranked.index(i)) for i,(r,v) in enumerate(zip(selected,y))]
    dump(D/'graded.json.gz',truth)
    dump(D/'results.json',dict(total=len(rows),evaluable=n,excluded=[r['id'] for r in rows if r['id'] not in direct],tasks=nt,repos=len(set(r['repo'] for r in selected)),task_sizes=dict(Counter(Counter(ids).values())),primary=table,curves=curves,positive_tasks=len(set(ids[y])),positive_repositories=len(set(r['repo'] for r,a in zip(selected,y) if a)),graded_files={v:digest(R12/v) for v in ['outcomes.json.gz','independent_blob_checks.json.gz']}))
    for a in policies:
        c=table[a];print(a,c['reused'],c['unsafe_reused'],c['risk'],round(c['expected_task_matched_errors'],3))
if __name__=='__main__':main()
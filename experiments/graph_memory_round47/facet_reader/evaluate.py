"""Join sealed forecasts with official roles and measure paired repository-level effects."""
from features import *
import sys
from sklearn.metrics import average_precision_score
sys.path.insert(0,str(W/'memory_session5/serbench/upstream/src'))
from serbench import _reference_scorer as native
from collections import defaultdict
METRICS=['MSS5','MSS8','MSS8_under2048','MSS8_under6144','Group5','Group8','Necessity5','MSS_unlimited_2048','MSS_unlimited_6144']
def score(r,truth):
    seq=set(r);h=[len(seq.intersection(g[2]))>=g[0] for g in truth['groups']];den=sum(w for k,w,g in truth['groups'])
    return [int(all(h) or any(set(a)<=seq for a in truth['alts'])),sum(h)/len(h) if h else 1.,
            sum(p[1]*c for p,c in zip(truth['groups'],h))/den if den else float(not h)]
def raw(q,st,lb,feature):
    ids=st['ids'];idx={k:j for j,k in enumerate(ids)};cost=dict(zip(feature['ids'],feature['qw']))
    t=dict(cost=[cost[k] for k in ids],groups=[[g['minimum_required'],g['necessity_weight'],[idx[k] for k in g['acceptable_evidence_ids'] if k in idx]] for g in lb['required_evidence_groups']],
           alts=[[idx[k] for k in a] for a in lb['alternative_minimal_sets'] if all(k in idx for k in a)],roles=[role(g['role']) for g in lb['required_evidence_groups']])
    temp=native.ideal_group_dcg;memo={};a={};checks=0
    def cached(groups,weights,k):
        if k not in memo:memo[k]=temp(groups,weights,k)
        return memo[k]
    native.ideal_group_dcg=cached
    try:
        for method,r in st['rank'].items():
            c=np.asarray(t['cost'])[r].cumsum();k5,k6=[int((c<=cap).sum()) for cap in [2048,6144]];lens=[5,8,min(8,k5),min(8,k6),k5,k6];vals=[score(r[:k],t) for k in lens]
            v=[z[0] for z in vals[:4]]+[vals[0][1],vals[1][1],vals[0][2],vals[4][0],vals[5][0]]
            for i,k in enumerate((5,8)):
                o=native.score_prediction([ids[j] for j in r[:k]],lb,k)
                assert np.isclose(o[f'mss_complete@{k}'],v[i]) and np.isclose(o[f'group_recall@{k}'],v[4+i])
                if k==5:assert np.isclose(o['necessity_weighted_recall@5'],v[6])
                checks+=1
            a[method]=dict(metric=v,items=lens,tokens=[int(c[k-1]) if k else 0 for k in lens])
    finally:native.ideal_group_dcg=temp
    return t,dict(repo=st['repo'],arms=a),checks
def summarize(qs,pred,out):
    repos,ix=np.unique([out[q]['repo'] for q in qs],return_inverse=True);n=len(repos);count=np.bincount(ix);arms=sorted(set.intersection(*(set(out[q]['arms']) for q in qs)))
    M=np.array([[out[q]['arms'][a]['metric'] for a in arms] for q in qs]);agg=np.zeros((n,len(arms),len(METRICS)));np.add.at(agg,ix,M);ar=agg/count[:,None,None]
    arm={a:dict(total=M[:,i].sum(0).tolist(),macro=ar[:,i].mean(0).tolist(),tokens=np.mean([out[q]['arms'][a]['tokens'] for q in qs],axis=0).tolist(),
                items=np.mean([out[q]['arms'][a]['items'] for q in qs],axis=0).tolist()) for i,a in enumerate(arms)}
    rng=np.random.default_rng(4721401);draw=rng.multinomial(n,np.repeat(1/n,n),size=20000);sz=draw@count
    pairs=[]
    for base in ('bm','qwen'):
        if base not in arms:continue
        comps=[base+'_static',base+'_placebo',base,base+'_union',base+'_lex']
        if base=='qwen':comps+=['dpp','mmr']
        for s in ('','_mask'):
            pairs.extend([(base+'_dynamic'+s,b+s) for b in comps])
            pairs.extend([(base+'_static'+s,base+s),(base+'_union'+s,base+s)])
    flags={}
    for a,b in pairs:
        i,j=arms.index(a),arms.index(b);dr=agg[:,i]-agg[:,j];d=M[:,i]-M[:,j];mr=ar[:,i]-ar[:,j]
        flags[a+' minus '+b]=dict(micro=d.mean(0).tolist(),macro=mr.mean(0).tolist(),ci=np.quantile((draw@dr)/sz[:,None],[.025,.975],axis=0).tolist(),macroci=np.quantile((draw@mr)/n,[.025,.975],axis=0).tolist(),
              wins=(d>1.e-10).sum(0).tolist(),loss=(d< -1.e-10).sum(0).tolist(),set5=sum(set(pred[q]['rank'][a][:5])!=set(pred[q]['rank'][b][:5]) for q in qs))
    return dict(states=len(qs),repos=n,arms=arm,contrasts=flags)
def diagnostics(qs,pred,prob,lb):
    state_target=[];candidate_target=[];state_pred=[];candidate_pred=[];aps=defaultdict(list);rt=Counter()
    for q in qs:
        y,z=targets(pred[q]['ids'],lb[q]);vp=np.array(prob[q]['p']);state_target.append(z);candidate_target.append(y);candidate_pred.append(vp);state_pred.append(prob[q]['demand'])
        rr=[role(g['role']) for g in lb[q]['required_evidence_groups']];rt['multigroup']+=len(rr)>1;rt['multirole']+=len(set(rr))>1;rt['repeat_role']+=len(set(rr))<len(rr)
        for k in range(4):
            if y[:,k].any():aps[k].append(average_precision_score(y[:,k],vp[:,k]))
    ys=np.stack(state_target);yd=np.concatenate(candidate_target);ps=np.stack(state_pred);pd=np.concatenate(candidate_pred)
    def metric(y,p):
        return dict(positive=int(y.sum()),n=len(y),prevalence=float(y.mean()),AP=float(average_precision_score(y,p)) if y.any() else None)
    return dict(count=dict(rt),roles=[dict(role=ROLES[k],state=metric(ys[:,k],ps[:,k]),candidate=metric(yd[:,k],pd[:,k]),within_eligible_AP=float(np.mean(aps[k])) if aps[k] else None) for k in range(4)])
def main():
    frozen=read(D/'seal.json')
    for name,k in [('predictions.json.gz','pred'),('predicted-roles.json.gz','numbers'),('model.json','model'),('panels.json','panels')]:assert sha(D/name)==frozen[k]
    pred=read(D/'predictions.json.gz');p=read(D/'predicted-roles.json.gz');qs=read(D/'panels.json');feat=read(R34/'features.json.gz');gold=labels(set(pred))
    od={};jud={};checks=0
    for q,st in pred.items():
        jud[q],od[q],n=raw(q,st,gold[q],feat[q]);checks+=n
    write('outcomes.json.gz',od);write('ordinal-judgments.json.gz',jud)
    ps={name:summarize(qs[name],pred,od) for name in ('dev','test','outside','pilot')};diag={name:diagnostics(qs[name],pred,p,gold) for name in ('dev','test','outside','pilot')}
    # Gold-dependent exploratory breakdown occurs strictly after forecasts, with role labels used only for scoring.
    outside=qs['outside'];byarity={}
    for m in [False,True]:
        ids=[q for q in outside if (len(set(jud[q]['roles']))>1)==m]
        byarity[str(m)]=summarize(ids,pred,od)
    write('results.json',dict(panels=ps,diagnostics=diag,arity=byarity,metrics=METRICS,scorer=sha(Path(native.__file__)),checks=checks,
                               seal=sha(D/'seal.json'),outcomes=sha(D/'outcomes.json.gz'),jud=sha(D/'ordinal-judgments.json.gz')))
    print('Scored',len(pred),'states and',checks,'native prefixes.')
if __name__=='__main__':main()


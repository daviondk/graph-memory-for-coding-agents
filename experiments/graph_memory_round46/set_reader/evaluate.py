"""Score sealed rankings, compute native group/MSS metrics, and cluster all paired differences by repository."""
from core import *
import sys
sys.path.insert(0,str(W/'memory_session5/serbench/upstream/src'))
from serbench import _reference_scorer as official
METRICS=('MSS5','MSS8','MSS8_2048','MSS8_6144','Group5','Group8','Necessity5','MSS_unlimited_2048','MSS_unlimited_6144')
PAIRS=(('dpp','qwen'),('dpp','mmr'),('dpp_mask','qwen_mask'),('history','dpp_mask'),('history','historic_static'),('dpp_mask','mmr_mask'))
def calculus(ids,row):
    top=set(ids);terms=row['groups']
    if not terms:return 1.,1.,1.
    hit=[len(top.intersection(members))>=quota for quota,w,members in terms]
    weights=[w for quota,w,mem in terms];sw=sum(weights)
    return (int(all(hit) or any(set(seq)<=top for seq in row['alternative'])),np.mean(hit),sum(w*z for w,z in zip(weights,hit))/sw if sw else 0.)
def one(order,row):
    c=np.asarray([row['cost'][i] for i in order]).cumsum()
    k=[5,8,*[min(8,int((c<=b).sum())) for b in (2048,6144)],*[int((c<=b).sum()) for b in (2048,6144)]]
    scores=[calculus(order[:n],row) for n in k];metric=[v[0] for v in scores[:4]]+[scores[0][1],scores[1][1],scores[0][2]]+[v[0] for v in scores[4:]]
    return dict(metric=metric,tokens=[int(c[n-1]) if n else 0 for n in k],items=k)
def summarize(qs,R,rank,pairs):
    arms=sorted(set.intersection(*(set(R[q]['arms']) for q in qs)))
    names,groups=np.unique([R[q]['repo'] for q in qs],return_inverse=True);n=len(names);freq=np.bincount(groups)
    M=np.array([[R[q]['arms'][s]['metric'] for s in arms] for q in qs]);g=np.zeros((n,len(arms),len(METRICS)));np.add.at(g,groups,M)
    gen=np.random.default_rng(4621406);boot=gen.multinomial(n,np.full(n,1/n),size=20000)
    a={};d={}
    for i,name in enumerate(arms):
        a[name]=dict(sum=M.sum(0)[i].tolist(),mean=M.mean(0)[i].tolist(),macro=(g[:,i]/freq[:,None]).mean(0).tolist(),
                     tokens=np.mean([R[q]['arms'][name]['tokens'] for q in qs],axis=0).tolist(),items=np.mean([R[q]['arms'][name]['items'] for q in qs],axis=0).tolist())
    for v,b in pairs:
        i,j=arms.index(v),arms.index(b);d0=M[:,i]-M[:,j];dg=g[:,i]-g[:,j];macro=dg/freq[:,None];wt=boot@freq
        d[v+' minus '+b]=dict(micro=d0.mean(0).tolist(),macro=macro.mean(0).tolist(),wins=(d0>1e-10).sum(0).tolist(),loss=(d0< -1e-10).sum(0).tolist(),
          ci=np.quantile((boot@dg)/wt[:,None],[.025,.975],axis=0).tolist(),macro_ci=np.quantile((boot@macro)/n,[.025,.975],axis=0).tolist(),
          changed_order5=sum(rank[q][v][:5]!=rank[q][b][:5] for q in qs),changed_set5=sum(set(rank[q][v][:5])!=set(rank[q][b][:5]) for q in qs))
    return dict(states=len(qs),repos=n,arms=a,paired=d)
def main():
    pred=read(D/'forecasts.json.gz');neural=read(D/'reranker-scores.json.gz');rp=read(D/'reranker-seal.json')
    assert sha(D/'reranker-scores.json.gz')==rp['data'] and sha(D/'forecasts.json.gz')==read(D/'forecast-seal.json')['data']
    panel=signed(P,'panel.json');gold=signed(P,'cal-ordinal-judgments.json.gz');R={};rank={};check=0;copy={}
    for q,v in pred.items():
        native=gold[q];indexes={s:j for j,s in enumerate(v['ids'])};byid={i:indexes[t] for i,t in enumerate(native['ids'])}
        row=dict(cost=[dict(zip(native['ids'],native['cost']))[s] for s in v['ids']],
                 groups=[[k,w,[byid[i] for i in ids]] for k,w,ids in native['groups']],alternative=[[byid[i] for i in alt] for alt in native['alternative']])
        copy[q]=row;order=v['rank'].copy()
        if q in neural:order['neural']=neural[q]['rank']
        rank[q]=order;results={m:one(rr,row) for m,rr in order.items()}
        # Native scorer is called only at fixed native depths; avoid recomputing ideal grouped DCG for the same state/k.
        g=dict(required_evidence_groups=[dict(minimum_required=k,necessity_weight=w,acceptable_evidence_ids=ids,role=str(j)) for j,(k,w,ids) in enumerate(row['groups'])],alternative_minimal_sets=row['alternative'])
        orig=official.ideal_group_dcg;memo={}
        def ideal(terms,weights,k):
            if k not in memo:memo[k]=orig(terms,weights,k)
            return memo[k]
        official.ideal_group_dcg=ideal
        try:
            for m,rr in order.items():
                s=results[m]['metric']
                for k,j in ((5,0),(8,1)):
                    o=official.score_prediction(rr,g,k);assert np.isclose(o[f'mss_complete@{k}'],s[j]) and np.isclose(o[f'group_recall@{k}'],s[4+j])
                    if k==5:assert np.isclose(o['necessity_weighted_recall@5'],s[6])
                    check+=1
        finally:official.ideal_group_dcg=orig
        R[q]=dict(repo=v['repo'],seen=sum(v['seen']),arms=results)
    write('audit-judgments.json.gz',copy);write('outcomes.json.gz',R)
    panels={}
    for n,qs in (('outside204',panel['remaining']),('all214',panel['order']),('pilot10',panel['pilot'])):
        panels[n]=summarize(qs,R,rank,PAIRS)
        if n=='outside204':
            for mode in (True,False):
                group=[q for q in qs if bool(R[q]['seen'])==mode]
                if group:panels[n+('_seen' if mode else '_unseen')]=summarize(group,R,rank,PAIRS)
    small=read(D/'small-panel.json');panels['neural12']=summarize(small,R,rank,(('neural','qwen'),('neural','dpp_top16'),('dpp_top16','qwen')))
    write('results.json',dict(metrics=METRICS,panels=panels,native_checks=check,scorer=sha(Path(official.__file__)),pred=sha(D/'forecast-seal.json'),
          neural=sha(D/'reranker-seal.json'),outcomes=sha(D/'outcomes.json.gz'),audit=sha(D/'audit-judgments.json.gz')))
    print('Scored',len(R),'states and',check,'native reference prefixes.')
if __name__=='__main__':main()

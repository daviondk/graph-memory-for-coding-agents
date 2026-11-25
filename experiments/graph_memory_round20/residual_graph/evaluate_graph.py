"""Evaluate individual matched rankings only after forecast seals exist."""
from collections import defaultdict
from statistics import mean
import dataclasses
from setup_graph import ROOT,R18,TR,load,put,pilot
from evaluate import compare
from verify_records import metrics as independent
from graph_memory.evaluation.span_metrics import span_mrr,span_metrics_at
def main():
    lock=load(ROOT/'forecast-seal.json')
    assert lock['plan']==pilot.sha(ROOT/'prediction-plan.json') and all(pilot.sha(ROOT/p)==v for p,v in lock['forecasts'].items())
    gp=R18/'isetrace_official/gold-spans.json.gz';gold=load(gp)
    T=defaultdict(dict);out=[];cal=[];budget=2048
    for fn in lock['forecasts']:
        which=fn.split('-')[1]
        for rec in load(ROOT/fn):
            q=rec['q'];t=rec['t'];labels=tuple(pilot.SourceSpan.model_validate(v) for v in gold[q])
            rr=tuple(pilot.RankedNodeRecord.model_validate(v) for v in rec['rr'])
            index={v.node_id:v for v in rr}
            assert len(index)==len(rr)
            for arm,keys in rec['arms'].items():
                subset=tuple(index[k] for k in keys);cost=sum(v.token_count for v in subset)
                assert cost<=budget and len(keys)==len(set(keys))
                measurement=pilot.span_metrics_under_token_budget(subset,labels,budget)
                if arm=='prefix':assert measurement==pilot.span_metrics_under_token_budget(rr,labels,budget)
                ms=independent(gold[q],[v.model_dump() for v in subset]);assert all(abs(getattr(measurement,k)-v)<1e-12 for k,v in zip(('coverage','density','full_support'),ms))
                result=dict(q=q,t=t,method=which,arm=arm,tokens=cost,nodes=len(keys),**dataclasses.asdict(measurement))
                key=which+'/'+arm;assert q not in T[key];T[key][q]=result;out.append(result)
            c={f'coverage_{b}':pilot.span_metrics_under_token_budget(rr,labels,b).coverage for b in (512,1024,2048)}
            cal.append(dict(q=q,t=t,method=which,recall_5=span_metrics_at(rr,labels,5).coverage,mrr=span_mrr(rr,labels),full_support_2048=T[which+'/prefix'][q]['full_support'],**c))
    assert all(set(values)==set(gold) for values in T.values())
    M={k:dict(n=len(v),hits=int(sum(x['full_support'] for x in v.values())),**{m:mean(x[m] for x in v.values()) for m in ('full_support','coverage','density','f1','tokens','nodes')}) for k,v in T.items()}
    pairs={}
    for w in ('rgcn','seed'):
        for a,b in [('related','skip'),('related','prefix'),('skip','prefix')]:
            ka=w+'/'+a;kb=w+'/'+b;pairs[ka+' - '+kb]=compare(T[ka],T[kb])
    for a in ('prefix','skip','related'):pairs['rgcn/'+a+' - seed/'+a]=compare(T['rgcn/'+a],T['seed/'+a])
    R19={r['q']:r for r in load(TR/'outcomes.json.gz') if r['arm']=='prefix'}
    pairs['seed/prefix - R19 standalone dense/prefix']=compare(T['seed/prefix'],R19)
    pub={'rgcn':[(.4952,.0075),(.6704,.0095),(.8188,.0049),(.7733,.0053),(.7876,.0109),(.6210,.0063)],
         'seed':[(.4759,.0053),(.6498,.0027),(.7849,.0046),(.7278,.0064),(.7167,.0039),(.5482,.0041)]}
    cols=['coverage_512','coverage_1024','coverage_2048','full_support_2048','recall_5','mrr']
    table={w:{col:dict(local=mean(r[col] for r in cal if r['method']==w),pub_mean=mu,pub_sd=sd) for col,(mu,sd) in zip(cols,ref,strict=True)} for w,ref in pub.items()}
    put(ROOT/'table2-rows.json.gz',cal);put(ROOT/'outcomes.json.gz',out)
    put(ROOT/'results.json',dict(metrics=M,contrasts=pairs,table2=table,gold_sha256=pilot.sha(gp),n=len(gold),trajectories=len({v['t'] for v in gold2rows(T)})))
    print({k:r['hits'] for k,r in M.items()},flush=True)
def gold2rows(T):return T['rgcn/prefix'].values()
if __name__=='__main__':main()


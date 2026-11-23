"""Evaluate all official log-spaced budget points without regenerating ranks."""
from collections import defaultdict
from statistics import mean
import sys
from project import ROOT,OFF,load,put,pilot
from graph_memory.evaluation.span_suite import normalized_budget_auc
from verify_records import metrics
from placebo import cluster_ci
B=(256,512,1024,2048,4096,8192)
A=('prefix','skip','value','related')
def plan():
    put(ROOT/'grid-plan.json',{n:pilot.sha(ROOT/n) for n in ('GRID_PROTOCOL_RU.md','budget_grid.py','plan-seal.json')})
def predict():
    assert all(pilot.sha(ROOT/n)==h for n,h in load(ROOT/'grid-plan.json').items())
    seal=load(ROOT/'forecast-seal.json')
    metadata=load(OFF/'placebo-event-metadata.json.gz');hashes={}
    for i in range(8):
        n=f'forecasts-main-{i}.json.gz';assert pilot.sha(ROOT/n)==seal['forecasts'][n]
        picks={}
        for r in load(ROOT/n):
            rr=tuple(pilot.RankedNodeRecord.model_validate(n) for n in r['rr'])
            ix={n.node_id:j for j,n in enumerate(rr)}
            meta={}
            for n in rr:
                cid,role,_=metadata[r['t']][n.source_spans[0].event_id]
                meta[n.node_id]=dict(call_id=str(cid) if cid>=0 else None,node_kind={'a':'content.tool_argument','o':'content.tool_output'}[role])
            one={str(b):{a:[ix[n.node_id] for n in pilot.pack(rr,meta,b,a)] for a in A} for b in B}
            assert all(r['arms'][a]==[rr[j].node_id for j in one['2048'][a]] for a in A)
            picks[r['q']]=one
        n=f'grid-picks-{i}.json.gz';put(ROOT/n,picks);hashes[n]=pilot.sha(ROOT/n)
    put(ROOT/'grid-seal.json',dict(forecast=pilot.sha(ROOT/'forecast-seal.json'),plan=pilot.sha(ROOT/'grid-plan.json'),files=hashes))
def score():
    lock=load(ROOT/'grid-seal.json');assert all(pilot.sha(ROOT/n)==h for n,h in lock['files'].items())
    gold=load(OFF/'gold-spans.json.gz')
    rows=[];aucs=defaultdict(dict);cells=defaultdict(list)
    for i in range(8):
        picks=load(ROOT/f'grid-picks-{i}.json.gz')
        for r in load(ROOT/f'forecasts-main-{i}.json.gz'):
            q=r['q'];one=picks[q];perq=defaultdict(dict)
            for b in B:
                for a in A:
                    pred=[r['rr'][j] for j in one[str(b)][a]];cost=sum(n['token_count'] for n in pred);assert cost<=b
                    cov,den,fs=metrics(gold[q],pred)
                    row=dict(q=q,t=r['t'],b=b,arm=a,coverage=cov,full_support=fs,density=den,tokens=cost)
                    rows.append(row);perq[a][b]=row;cells[b,a].append(row)
            for a in A:
                aucs[a][q]=dict(t=r['t'],**{k:normalized_budget_auc({b:perq[a][b][k] for b in B}) for k in ('coverage','full_support')})
    result={}
    for a in A:
        result[a]=dict(by_budget={str(b):{k:mean(r[k] for r in cells[b,a]) for k in ('full_support','coverage','density','tokens')} for b in B},
                       auc={m:mean(r[m] for r in aucs[a].values()) for m in ('full_support','coverage')})
    ci={}
    for a in ['prefix','skip','value']:
        ci[a]={m:cluster_ci([(v['t'],v[m]-aucs[a][q][m]) for q,v in aucs['related'].items()]) for m in ('full_support','coverage')}
    put(ROOT/'grid-outcomes.json.gz',rows);put(ROOT/'grid-results.json',dict(policies=result,related_minus_reference_auc_ci95=ci))
if __name__=='__main__':{'plan':plan,'predict':predict,'score':score}[sys.argv[1]]()

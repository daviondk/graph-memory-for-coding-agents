"""Native six-column Table 1 calibration; descriptor of replication, not benchmark tuning."""
from statistics import mean
from prepare import ROOT,OFF,load,put,pilot
from graph_memory.evaluation.span_metrics import span_metrics_at,span_mrr
PUBLISHED={'coverage_512':(.4760,.0052),'coverage_1024':(.6498,.0027),'coverage_2048':(.7849,.0046),'full_support_2048':(.7278,.0064),'recall_5':(.7171,.0039),'mrr':(.5484,.0045)}
def run():
    seal=load(ROOT/'forecast-seal.json');assert all(pilot.sha(ROOT/f)==h for f,h in seal['forecasts'].items())
    gt=load(OFF/'gold-spans.json.gz')
    rows=[]
    for f in seal['forecasts']:
        for r in load(ROOT/f):
            rr=tuple(pilot.RankedNodeRecord.model_validate(x) for x in r['rr']);gold=tuple(pilot.SourceSpan.model_validate(s) for s in gt[r['q']])
            metrics={}
            for b in [512,1024,2048]:
                m=pilot.span_metrics_under_token_budget(rr,gold,b);metrics[f'coverage_{b}']=m.coverage
                if b==2048:metrics['full_support_2048']=m.full_support
            metrics['recall_5']=span_metrics_at(rr,gold,5).coverage
            metrics['mrr']=span_mrr(rr,gold)
            rows.append(dict(q=r['q'],t=r['t'],**metrics))
    assert {r['q'] for r in rows}==set(gt)
    stats={}
    for k,(mu,sd) in PUBLISHED.items():
        obs=mean(r[k] for r in rows);stats[k]=dict(single_seed=obs,published_five_seed_mean=mu,published_five_seed_sd=sd,delta_points=(obs-mu)*100)
    put(ROOT/'table1-rows.json.gz',rows);put(ROOT/'table1.json',stats)
if __name__=='__main__':run()

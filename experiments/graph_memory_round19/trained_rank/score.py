"""Score only after all 2,000 source-only rankings and selections are sealed."""
from collections import defaultdict
from statistics import mean
import dataclasses
from prepare import ROOT,R18,OFF,load,put,pilot
from verify_records import metrics as independent
from evaluate import compare
def run():
    seal=load(ROOT/'forecast-seal.json');assert all(pilot.sha(ROOT/f)==h for f,h in seal['forecasts'].items())
    assert seal['plan']==pilot.sha(ROOT/'prediction-plan.json')
    gpath=OFF/'gold-spans.json.gz';truth=load(gpath)
    rankers={name:defaultdict(dict) for name in ('trained','frozen')};trained=rankers['trained'];out=[]
    for f in seal['forecasts']:
        for row in load(ROOT/f):
            q=row['q'];rr=tuple(pilot.RankedNodeRecord.model_validate(r) for r in row['rr'])
            gs=tuple(pilot.SourceSpan.model_validate(o) for o in truth[q]);node={a.node_id:a for a in rr}
            if row['partial']:
                n=pilot.RankedNodeRecord.model_validate(row['partial']);assert n.node_id not in node;node[n.node_id]=n
            for arm,keys in row['arms'].items():
                ns=tuple(node[k] for k in keys);used=sum(n.token_count for n in ns);assert used<=2048
                val=pilot.span_metrics_under_token_budget(ns,gs,2048)
                if arm=='prefix':assert val==pilot.span_metrics_under_token_budget(rr,gs,2048)
                ms=independent(truth[q],[r.model_dump() for r in ns]);assert all(abs(getattr(val,k)-v)<1e-12 for k,v in zip(('coverage','density','full_support'),ms))
                entry=dict(q=q,t=row['t'],group='main',arm=arm,tokens=used,nodes=len(ns),**dataclasses.asdict(val));assert q not in trained[arm];trained[arm][q]=entry;out.append(entry)
    assert all(set(v)==set(truth) for v in trained.values())
    for entry in load(R18/'isetrace_e5/outcomes.json.gz'):
        if entry['group']=='main':rankers['frozen'][entry['arm']][entry['q']]=entry
    stats={a:{m:mean(r[m] for r in rec.values()) for m in ('coverage','density','full_support','f1','tokens','nodes')}|dict(n=len(rec),fs_hits=int(sum(r['full_support'] for r in rec.values()))) for a,rec in trained.items()}
    pairs={a+'-'+b:compare(trained[a],trained[b]) for a,b in [('related','skip'),('related','prefix'),('related','clip'),('related','value'),('skip','prefix')]}
    for a in ('related','prefix'):pairs[a+'-frozen_'+a]=compare(trained[a],rankers['frozen'][a])
    put(ROOT/'outcomes.json.gz',out);put(ROOT/'results.json',dict(metrics=stats,paired=pairs,published_five_seed={'pu_dense_ft_fs_mean':.7278,'pu_dense_ft_fs_sd':.0064,
        'residual_rgcn_fs_mean':.7733,'residual_rgcn_fs_sd':.0053,'pu_dense_ft_coverage_mean':.7849,'pu_dense_ft_coverage_sd':.0046},
        gold_sha256=pilot.sha(gpath),frozen_outcomes_sha256=pilot.sha(R18/'isetrace_e5/outcomes.json.gz')))
    print(stats,flush=True)
if __name__=='__main__':run()

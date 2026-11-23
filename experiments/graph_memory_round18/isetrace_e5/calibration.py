"""Post-score, deliberately generous bounds for ordering uncertainty near the native stopping boundary."""
from collections import defaultdict
from statistics import mean
from project import ROOT,load,put,pilot
from verify_records import metrics
from project import OFF,CACHE
def run():
    gold=load(OFF/'gold-spans.json.gz');records=defaultdict(list)
    for i in range(8):
        cases=load(ROOT/f'forecasts-main-{i}.json.gz')
        repeated={}
        for r in cases:
            if r['t'] not in repeated:
                row=load(CACHE/'projection'/f"{i}-{r['t']}.json.gz")
                repeated[r['t']]={c['item_id']:c['text'] for c in row['pool']}
            text=repeated[r['t']];rr=r['rr'];n=len(r['arms']['prefix'])
            for eps in [0.0,1e-6,1e-4]:
                fixed=rr[:n];possible=rr[:n];amb=False
                if n<len(rr):
                    # Only the first overbudget score group can affect the chosen prefix.
                    a=b=n
                    while a>0 and rr[a-1]['score']-rr[a]['score']<=eps:a-=1
                    while b+1<len(rr) and rr[b]['score']-rr[b+1]['score']<=eps:b+=1
                    if a<b and len({text[k['node_id']] for k in rr[a:b+1]})>1:
                        fixed=rr[:a];slack=2048-sum(x['token_count'] for x in fixed)
                        possible=fixed+[c for c in rr[a:b+1] if c['token_count']<=slack];amb=True
                low=metrics(gold[r['q']],fixed);high=metrics(gold[r['q']],possible)
                records[str(eps)].append(dict(q=r['q'],lower_coverage=low[0],upper_coverage=high[0],lower_fs=low[2],upper_fs=high[2],ambiguous=amb))
    result={}
    for eps,rows in records.items():
        result[eps]={k:mean(r[k] for r in rows) for k in rows[0] if k not in ['q','ambiguous']}
        result[eps].update(boundary_cases=sum(r['ambiguous'] for r in rows),fs_nonconstant=sum(r['lower_fs']!=r['upper_fs'] for r in rows),coverage_nonconstant=sum(r['lower_coverage']!=r['upper_coverage'] for r in rows))
    put(ROOT/'calibration-bounds.json',result)
if __name__=='__main__':run()

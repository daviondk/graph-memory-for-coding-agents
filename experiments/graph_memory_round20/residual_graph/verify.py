"""Verify the release with Python 3.11+ standard library only; no model, GPU or dataset required."""
from pathlib import Path
from collections import defaultdict
from statistics import mean
import hashlib,gzip,json
ROOT=Path(__file__).resolve().parent
def get(p):
    src=p.read_bytes()
    return json.loads(gzip.decompress(src) if p.suffix=='.gz' else src)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def merged(spans):
    parts=defaultdict(list)
    for s in spans:parts[s['event_id'],s['json_pointer']].append((s['char_start'],s['char_end']))
    unique={}
    for key,intervals in parts.items():
        dest=[]
        for a,b in sorted(intervals):
            if dest and a<=dest[-1][1]:dest[-1]=(dest[-1][0],max(dest[-1][1],b))
            else:dest.append((a,b))
        unique[key]=dest
    return unique
def metric(gold,selected):
    spans=[s for n in selected for s in n['source_spans']];recovered=merged(spans)
    common=sum(max(0,min(b,v)-max(a,u)) for k,ints in gold.items() for a,b in ints for u,v in recovered.get(k,()))
    target=sum(b-a for ints in gold.values() for a,b in ints);display=sum(s['char_end']-s['char_start'] for s in spans)
    coverage=common/target;density=common/display if display else 0.
    return dict(coverage=coverage,density=density,f1=2*coverage*density/(coverage+density) if common else 0,
                full_support=int(common==target),nodes=len(selected),tokens=sum(n['token_count'] for n in selected))
def pack(order,pool,calls,how,budget=2048):
    used=0;selected=[]
    for place,k in enumerate(order):
        n=pool[k]['token_count']
        if n+used>budget:break
        used+=n;selected.append(k)
    else:return selected
    if how=='prefix':return selected
    tail=order[place:]
    if how=='related':
        other={'content.tool_output':'content.tool_argument','content.tool_argument':'content.tool_output'}
        links={(call,kind) for k in selected for call,kind in [calls[k]] if call}
        tail=sorted(tail,key=lambda k:(calls[k][0],other.get(calls[k][1])) not in links)
    for k in tail:
        n=pool[k]['token_count']
        if used+n<=budget:selected.append(k);used+=n
    return selected
def check(result,record):
    assert all(abs(x-record[k])<1e-12 for k,x in result.items())
def main():
    man=get(ROOT/'MANIFEST_SHA256.json')
    assert all(sha(ROOT/k)==v for k,v in man.items())
    seal=get(ROOT/'forecast-seal.json');assert all(sha(ROOT/k)==v for k,v in seal['forecasts'].items()) and seal['plan']==sha(ROOT/'prediction-plan.json')
    d=get(ROOT/'dev500-pu-dense-lock.json');assert d['ranks']==sha(ROOT/'dev500-pu-dense-ranks.json.gz') and d['n']==500
    gold={q:merged(g) for q,g in get(ROOT/'gold-spans.json.gz').items()}
    calls=get(ROOT/'candidate-call-map.json.gz');assert len(calls)==1207
    native=get(ROOT/'results.json');raw=get(ROOT/'outcomes.json.gz');out={(r['method'],r['q'],r['arm']):r for r in raw}
    assert len(out)==12000 and len(raw)==len(out)
    tables={(r['method'],r['q']):r for r in get(ROOT/'table2-rows.json.gz')}
    primary={}
    for filename in seal['forecasts']:
        method=filename.split('-')[1]
        for r in get(ROOT/filename):
            q,t=r['q'],r['t'];pool={n['node_id']:n for n in r['rr']};order=[n['node_id'] for n in r['rr']]
            assert len(order)==len(pool) and set(order)==set(calls[t]) and order==sorted(order,key=lambda k:(-pool[k]['score'],k))
            if method=='rgcn':primary[q]=(t,pool,order)
            g=gold[q];tab=tables[method,q]
            for b in [512,1024,2048]:
                pr=pack(order,pool,calls[t],'prefix',b);v=metric(g,[pool[k] for k in pr])
                assert abs(v['coverage']-tab[f'coverage_{b}'])<1e-12
            assert abs(metric(g,[pool[k] for k in order[:5]])['coverage']-tab['recall_5'])<1e-12
            first=next((1/i for i,k in enumerate(order,1) if metric(g,[pool[k]])['coverage']>0),0.)
            assert abs(first-tab['mrr'])<1e-12
            for a,chosen in r['arms'].items():
                assert pack(order,pool,calls[t],a)==chosen
                v=metric(g,[pool[k] for k in chosen]);assert v['tokens']<=2048
                check(v,out[method,q,a])
    assert set(primary)==set(gold) and len(tables)==4000
    for k,summary in native['metrics'].items():
        w,a=k.split('/');recs=[r for r in raw if r['method']==w and r['arm']==a];assert len(recs)==summary['n']
        assert int(sum(r['full_support'] for r in recs))==summary['hits']
        for m in ['full_support','coverage','density','f1','tokens','nodes']:assert abs(mean(r[m] for r in recs)-summary[m])<1e-12
    for w,stats in native['table2'].items():
        rows=[v for (k,_),v in tables.items() if k==w]
        for m,val in stats.items():assert abs(mean(r[m] for r in rows)-val['local'])<1e-12
    sub=ROOT/'topology';lock=get(sub/'forecast-seal.json');assert lock['out']==sha(sub/'forecasts.json.gz')
    raw_top=get(sub/'outcomes.json.gz');rows={(r['method'],r['q']):r for r in raw_top}
    for r in get(sub/'forecasts.json.gz'):
        q=r['q'];t,pool,orig=primary[q];g=gold[q]
        for name,order in r['orders'].items():
            assert len(order)==len(pool) and set(order)==set(pool)
            chosen=pack(order,pool,calls[t],'prefix')
            assert chosen==r['chosen'][name]
            check(metric(g,[pool[k] for k in chosen]),rows[name,q])
    assert len(rows)==6000
    for arm,stats in get(sub/'results.json')['metrics'].items():
        data=[r for r in raw_top if r['method']==arm];assert stats['hits']==sum(r['full_support'] for r in data)
    c=get(ROOT/'checkpoint.json');assert sha(ROOT/'best.pt')==c['sha'] and len(c['records'])==15 and c['global_steps']==465
    assert len(get(ROOT/'train-pairs.json.gz'))==get(ROOT/'pair-inventory.json')['total']
    print('Verified',len(man),'file hashes, 2000 matched test candidate universes, 12000 primary and 6000 topology readings, 4000 Table 2 rows, and the released native checkpoint.')
if __name__=='__main__':main()


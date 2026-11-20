"""Replay allocation options, cumulative budgets, independent scores and predeclared contrasts."""
import collections,gzip,hashlib,json,statistics,sys,time
from pathlib import Path
from allocation_run import D,ROOT,ARMS,labels,rows,source,incoming,simulate,evaluate
from common import pages
from pipeline import snapshots
from analyze import interval
from policy import BUDGETS,cost,costs,render,features,order,CAP,proposals,joint_fill
from verify import load,verify_filemap
def main():
    lock=load(D/'prediction_lock.json');verify_filemap(lock);cal=load(D/'training.json');exp=load(D/'results.json')
    fixed=load(ROOT/'selection.json');rosters=[fixed['train'],fixed['test'],load(ROOT/'transfer/selection.json'),load(D/'selection.json')]
    ig=[{i for i,k,r in arr} for arr in rosters]
    assert all(len(g)==len(rs) for g,rs in zip(ig,rosters)) and all(not g&h for j,g in enumerate(ig) for h in ig[j+1:])
    assert all(int(hashlib.sha256(('compact-s4|'+i).encode()).hexdigest(),16)%10 for g in ig for i in g)
    repos=[{i.split('.')[0] for i in s} for s in ig];assert not repos[1]&repos[3]
    actual=list(rows(D/'decisions.jsonl.gz'));ops=list(incoming('test'));assert actual==simulate(ops,cal['price'],cal['page_tertiles'])
    gold=labels('test');res,casewise=evaluate(actual,gold)
    assert all(exp[k]==v for k,v in res.items()) and casewise==list(rows(D/'metrics.jsonl.gz'))
    for a,stored in exp['value_contrasts'].items():assert interval(casewise,'value',a,'repo','alloc')==stored
    inclusive={k:dict(v,accepted=True) for k,v in gold.items()};ri,ci=evaluate(actual,inclusive)
    step=collections.Counter();token_all='--tokens' in sys.argv;sampled=0;ob=iter(ops)
    model=load(ROOT/'transfer/model.json');ts=collections.defaultdict(list)
    for k in range(8):
        for q in source('test',k):
            iid=q['instance'];balance={a:0 for a in ('scheduled','demand','value')};spent=collections.Counter();seen=0
            for t,stock,meta in snapshots(q):
                o=next(ob);act=actual[sum(step.values())]['actions'];assert (o['id'],o['cut'])==(iid,t);step[k]+=1;seen+=1
                baseline=o['choices']['512']['cost']
                for a,z in act.items():
                    y=o['choices'][str(z['budget'])];assert z['cost']==y['cost']<=z['budget'];spent[a]+=z['cost'];assert z['cumulative']==spent[a]
                    if a in balance:
                        balance[a]=min(balance[a]+baseline,1536)-z['cost'];assert balance[a]==z['balance'] and balance[a]>=0 and spent[a]<=act['fixed512']['cumulative']
                # Independent all-cost re-tokenization, optional. Timed lookups share tokenization cache.
                sampled_cut=int(hashlib.sha256((iid+'|'+str(t)+'|audit').encode()).hexdigest(),16)%40==0
                if token_all or sampled_cut:
                    pg=pages(stock['rebase']);assert len(pg)==o['pages']
                    for y in o['choices'].values():assert cost('\n'.join(render(pg[i]) for i in y['pages']))==y['cost']
                    if sampled_cut:
                        sampled+=1;start=time.perf_counter_ns()
                        cs=costs(pg);fs=features(pg,meta,t,q['issue'],order(pg,meta)[:CAP]);props=proposals(pg,fs,model)
                        common=time.perf_counter_ns()-start;side={}
                        for b in [512,256,1024]:
                            t0=time.perf_counter_ns();ids,n=joint_fill(pg,cs,props,b);pt=o['choices'][str(b)];assert ids==pt['pages'] and n==pt['cost']
                            val=sum(v for span,v in props.items() if set(span).issubset(ids));assert abs(val-pt['mass'])<1e-9
                            side[b]=time.perf_counter_ns()-t0
                        ts['fixed_ms'].append((common+side[512])/1e6);ts['all_three_ms'].append((common+sum(side.values()))/1e6)
    assert next(ob,None) is None
    out={'selected_instances':list(map(len,ig)),'repos':list(map(len,repos)),'distinct_c_prefixes':sum(step.values()),'all_eligible_intents':len(gold),'all_intent_hits':ri['hits'],'all_intent_value_minus_fixed512':interval(ci,'value','fixed512','repo','alloc'),'audited_choice_timings':sampled,'median_cpu_ms':{a:statistics.median(ls) for a,ls in ts.items()},'tokens_verified':token_all}
    if '--write-report' in sys.argv:(D/'audit.json').write_text(json.dumps(out,indent=1))
    else:
        old=load(D/'audit.json')
        for name in ('selected_instances','repos','distinct_c_prefixes','all_eligible_intents','all_intent_hits','all_intent_value_minus_fixed512','audited_choice_timings'):assert old[name]==out[name]
    print('PASS',out)
if __name__=='__main__':main()

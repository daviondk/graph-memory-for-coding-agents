"""Paired warm-filesystem time of supplying an answer from both versions, including obtaining the change feed."""
from collections import defaultdict,Counter
import collections,gzip,json,random,statistics,time
from extract import D,get,save,gz
from engine import unpack,scan,counter,hkey
from objects import git
def pool(rows):return [r for r in rows if not r['skip_reason'] and r.get('oracle') and r['relation']=='direct' and r['support']!='no_prior_root_witness']
def run(r,method):
    k=r['key'];p=r['repo'];a,b=r['old'],r['new'];s,time_start=0,time.perf_counter_ns();diff_ns=diff_bytes=search_ns=0
    if method=='full':reread=True
    else:
        z=counter(p,a,b,k,r['old_scope'],method);diff_ns=z['entire_ns'];diff_bytes=z['git_output_bytes'];reread=z['trigger']
    if reread:
        hit,search_ns,s,_=scan(p,b,k,r['new_scope'])
    else:hit=False
    return {'reread':reread,'value':hit,'wall_ns':time.perf_counter_ns()-time_start,'diff_ns':diff_ns,'search_ns':search_ns,'diff_stdout':diff_bytes,'lookup_stdout':s}
if __name__=='__main__':
    cases=pool(unpack('outcomes.json.gz'))
    assert len({hkey(r) for r in cases}) == len(cases)
    arms=['full','scope','exact','pickaxe'];rng=random.Random(214605)
    order=[(n,r,m) for r in cases for m in arms for n in range(3)]
    rng.shuffle(order)
    rows=[]
    for j,(n,r,m) in enumerate(order,1):
        value=run(r,m);rows.append({'id':hkey(r),'repo':r['repo'],'rep':n,'method':m,**value})
        if j%240==0:print(j,'of',len(order),flush=True)
    gz('timing_rows.json.gz',rows)
    by={};notes={hkey(r):r for r in cases}
    for m in arms:
        xs=[v for v in rows if v['method']==m]; block=defaultdict(list)
        for v in xs:block[v['id']].append(v)
        def totals(kind):return sum(statistics.median(v[kind] for v in z) for z in block.values())
        med=[statistics.median(v['wall_ns'] for v in z)/1e6 for z in block.values()]
        by[m]={'n':len(cases),'reps':3,'per_query_median_ms':statistics.median(med) if med else None,'sum_of_within_query_median_ms':sum(med),'query_minmax_ms':[min(med),max(med)] if med else [],'sum_median_diff_ms':totals('diff_ns')/1e6,'sum_median_search_ms':totals('search_ns')/1e6,'diff_bytes':sum(z[0]['diff_stdout'] for z in block.values()),'incorrect':sum(v['value']!=notes[v['id']]['oracle']['new']['hit'] for v in xs)}
    save('timing.json',{'arms':by,'unit':'one requested lookup after a real update','order_seed':214605,'cache':'offline complete Git objects, warm OS cache, one process per git invocation, serial shuffled order, no flush','version':git(cases[0]['repo'],'--version').stdout.decode().strip() if cases else None})
    print(by)

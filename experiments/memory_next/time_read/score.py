"""Score frozen rankings and responses against the independent relation table."""
import hashlib
from collections import defaultdict
import csv
import math
import random
from predict import ROOT,OLD,BASE,read,save,table

def effect(rows,m,b):
    values=[r[m]-r[b] for r in rows];w=values.count(1);l=values.count(-1)
    groups=defaultdict(list)
    for r,v in zip(rows,values):groups[r['repo']].append(v)
    totals=[(sum(v),len(v)) for v in groups.values()]
    rng=random.Random(20261116);boot=[]
    for _ in range(5000):
        z=rng.choices(totals,k=len(totals))
        boot.append(sum(x[0] for x in z)/sum(x[1] for x in z))
    boot.sort()
    return {'wins':w,'losses':l,'repo_ci95':[boot[125],boot[4874]],'delta':sum(values)/len(values),'exact_p':min(1,2*sum(math.comb(w+l,k) for k in range(min(w,l)+1))/2**(w+l))}
def main():
    for n,h in read(ROOT/'end_lock.json').items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    qs=table(BASE/'transfer/query_times_lite.csv');lib={r['trace_key']:r['instance_id'] for r in table(BASE/'transfer/source_times_lite.csv')}
    from collections import OrderedDict
    relations=table(OLD/'evaluation_relations.csv');g=defaultdict(list)
    for r in relations:
        if r['experience_instance_id'] not in g[r['related_instance_id']]:g[r['related_instance_id']].append(r['experience_instance_id'])
    choices={(v['ordinal'],v['arm']):v for v in read(ROOT/'blind_decisions.json')}
    rows=[]; metrics=set()
    for x in read(ROOT/'blind_lists.json'):
        i=x['ordinal'];t=qs[i];assert int(t['ordinal'])==i
        expected=set(g[t['target']]);assert expected
        pool=x['eligible'];linked=sum(lib[k] in expected for k in pool)
        r={'ordinal':i,'id':t['target'],'repo':t['repo'],'pr':t['target_pr'],'pool':len(pool),'linked':linked,'chance':linked/len(pool) if pool else 0.0}
        for m,order in x['ranks'].items():
            for k in [1,5]:
                label=m+'_'+str(k);metrics.add(label);r[label]=int(any(lib[j] in expected for j in order[:k]))
        for m in ['hyb_real','online_fields']:
            j=choices[(i,m)]['choice'];k=m+'_qwen';metrics.add(k);r[k]=int(lib.get(j) in expected);r[k+'_last']=int(lib.get(j)==g[t['target']][-1])
        rows.append(r)
    with (ROOT/'per_query.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    out={}
    for name,ss in [('all',rows),('label_available',[r for r in rows if r['linked']]),('available_competing',[r for r in rows if r['linked'] and r['pool']>=2]),('available_5plus',[r for r in rows if r['linked'] and r['pool']>=5])]:
        out[name]={'n':len(ss),'repos':len({r['repo'] for r in ss}),'distinct_pr':len({(r['repo'],r['pr']) for r in ss}),'chance_expected_hits':sum(r['chance'] for r in ss),'hits':{m:sum(r[m] for r in ss) for m in sorted(metrics|{'hyb_real_qwen_last','online_fields_qwen_last'})}}
        if ss:out[name]['hyb_reader_vs_rank']=effect(ss,'hyb_real_qwen','hyb_real_1')
    calls=[__import__('json').loads(line) for line in (ROOT/'calls.jsonl').read_text(encoding='utf8').splitlines()]
    out['costs']={'actual_calls':len(calls),'input':sum(c['usage']['prompt_tokens'] for c in calls),'output':sum(c['usage']['completion_tokens'] for c in calls),'empty':sum(r['pool']==0 for r in rows),'singleton':sum(r['pool']==1 for r in rows)}
    save(ROOT/'results.json',out);print(out['all']);print(out['costs'])
if __name__=='__main__':main()


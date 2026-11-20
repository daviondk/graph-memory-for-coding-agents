"""Offline evaluation of pre-task selection from published realized memory strategies."""
from pathlib import Path
import collections,csv,gzip,hashlib,io,json,math,random,statistics,tarfile
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'sources'
ARMS=('Observation Masking','LLM-Summary','Raw Agent')
def H(text):return int(hashlib.sha256(text.encode()).hexdigest(),16)
def csvrows(name):
    with (SRC/name).open(encoding='utf8',newline='') as fp:return list(csv.DictReader(fp))
def save(name,obj):
    b=json.dumps(obj,indent=1,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()
    (ROOT/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith('.gz') else b)
def source():
    tables=csvrows('paired_ci_diffs_vs_raw.csv')
    groups={}
    for row in tables:
        groups[row['experiment_raw']]=row['group'];groups[row['experiment_other']]=row['group']
    reported={r['experiment']:r for r in csvrows('bootstrapped_cis.csv')}
    data=collections.defaultdict(lambda:collections.defaultdict(dict));allrows=csvrows('experiment_instance_costs_sweagent.csv')
    audit={}
    with tarfile.open(SRC/'eval_results-swe_agent.tar','r:gz') as arc:
        members=[m for m in arc if m.isfile()]
        for experiment,group in groups.items():
            rlist=[r for r in allrows if r['experiment']==experiment]
            matches=[m for m in members if m.name.endswith(experiment+'.json')]
            assert len(matches)==1
            report=json.load(arc.extractfile(matches[0]));solves=set(report['resolved_ids'])
            for r in rlist:
                i=r['instance_id'];a=r['strategy'];y=int(i in solves);assert int(r['outcome'])==y
                assert a not in data[group][i]
                data[group][i][a]={'y':y,'c':float(r['cost'])+float(r['summary_cost']),'turns':int(r['turn_count'])}
            published=reported[experiment]
            audit[experiment]={'resolved':len(solves),'nominal_issues':report['total_instances'],'rows':len(rlist),
                'n_bootstrap_table':int(published['n_instances']),'solve_rate_published':float(published['solve_rate']),
                'nominal_rate':len(solves)/report['total_instances'],'author_mean_cost':float(published['mean_cost']),
                'approximate_summed_cost_per_nominal':sum(float(r['cost'])+float(r['summary_cost']) for r in rlist)/report['total_instances']}
    return data,audit
def stats(rows):
    return {'n':len(rows),'solves':sum(r['y'] for r in rows),'cost':sum(r['c'] for r in rows),'mean_cost':statistics.mean(r['c'] for r in rows),'turns':sum(r['turns'] for r in rows)}
def choose(scores):return max(ARMS,key=scores.__getitem__)
def cluster(rows,x,y):
    g=collections.defaultdict(list)
    for r in rows:g[r['repo']].append(r['p'][x]['y']-r['p'][y]['y'])
    grouped=[(sum(v),len(v)) for v in g.values()]
    rng=random.Random(51711);ds=[]
    for j in range(6000):
        picked=rng.choices(grouped,k=len(grouped));ds.append(sum(v for v,n in picked)/sum(n for v,n in picked))
    ds.sort();wins=sum(r['p'][x]['y']>r['p'][y]['y'] for r in rows);loss=sum(r['p'][x]['y']<r['p'][y]['y'] for r in rows)
    return {'wins':wins,'losses':loss,'diff':(wins-loss)/len(rows),'CI95':[ds[149],ds[5849]],'repo_clusters':len(grouped)}
def predict(group,usable,lam):
    records=[];ledgers=[];fmap={i:H('hist-mask5|'+i)%5 for i in usable}
    for f in range(5):
        train=sorted(i for i in usable if fmap[i]!=f);test=sorted(i for i in usable if fmap[i]==f)
        estimators={};stores={}
        for mode in ('one','full'):
            hist=[]
            for i in train:
                observed=(sorted(ARMS)[H('history-action5|'+group+'|'+i)%3],) if mode=='one' else ARMS
                hist.extend((i,a,usable[i][a]) for a in observed)
            assert not(set(i for i,_,_ in hist)&set(test))
            raw=[r['c'] for i,a,r in hist if a=='Raw Agent']
            denom=statistics.mean(raw or [r['c'] for _,_,r in hist])
            by=collections.defaultdict(list);global_hist=collections.defaultdict(list)
            for i,a,r in hist:
                v=r['y']-lam*r['c']/denom
                global_hist[a].append(v);by[i.rsplit('-',1)[0],a].append(v)
            global_scores={a:statistics.mean(global_hist[a]) for a in ARMS}
            estimators[mode+'global']=choose(global_scores)
            estimators[mode+'local']={i:choose({a:(sum(by[i.rsplit('-',1)[0],a])+8*global_scores[a])/(len(by[i.rsplit('-',1)[0],a])+8) for a in ARMS}) for i in test}
            stores[mode]={'observed_runs':len(hist),'cost_seen':sum(r['c'] for _,_,r in hist),'reference_raw_cost':denom,'selected_global':estimators[mode+'global']}
        ledgers.append({'fold':f,'actor':group,'test':len(test),'training_issues':len(train),'stores':stores})
        for i in test:
            ds=usable[i];choices={a:a for a in ARMS};choices['oracle_solve']=choose({a:ds[a]['y'] for a in ARMS})
            for mode in ('one','full'):
                choices[mode+'local']=estimators[mode+'local'][i];choices[mode+'global']=estimators[mode+'global']
            records.append({'actor':group,'fold':f,'id':i,'repo':i.rsplit('-',1)[0],'choices':choices,'p':{rule:ds[a] for rule,a in choices.items()}})
    return records,ledgers
def main():
    data,audit=source();save('source_check.json',audit);sensitivity={}
    for lam in (0.0,0.1,0.25):
        rec=[];ledgers=[];group_stats={};omitted={}
        for group,ds in sorted(data.items()):
            us={i:v for i,v in ds.items() if set(v)==set(ARMS)}
            omitted[group]=sorted(set(ds)-set(us))
            r,g=predict(group,us,lam);rec+=r;ledgers+=g
            group_stats[group]={a:stats([x['p'][a] for x in r]) for a in r[0]['p']}
        policies=list(rec[0]['p'])
        pooled={a:stats([x['p'][a] for x in rec]) for a in policies}
        macro={a:statistics.mean(v[a]['solves']/v[a]['n'] for v in group_stats.values()) for a in policies}
        contrasts={f'{x} vs {y}':cluster(rec,x,y) for x,y in [('onelocal','Observation Masking'),('onelocal','oneglobal'),('fulllocal','fullglobal'),('oneglobal','Observation Masking')]}
        k=str(lam);sensitivity[k]={'pooled':pooled,'macro_resolution':macro,'by_actor':group_stats,'contrasts':contrasts,'omitted':omitted}
        save('choices_'+k+'.json.gz',rec);save('history_'+k+'.json',ledgers)
    save('results.json',sensitivity)
    print(json.dumps(sensitivity['0.1']['pooled'],indent=1))
    print(json.dumps(sensitivity['0.1']['contrasts'],indent=1))
if __name__=='__main__':main()

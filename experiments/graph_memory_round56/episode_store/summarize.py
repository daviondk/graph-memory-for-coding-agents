"""Aggregate paired prequential decisions. Time blocks are technical replicates."""
from collections import defaultdict
import argparse
import random
from statistics import mean, median
from bench import BUDGETS, FIXED, HERE, LAYOUTS, PANELS, SEED, io, project

def quality(ranks,rows):
    recalls=[];hits=0
    for t,row in enumerate(rows):
        query=row[3]
        if query:
            gold=query[1]
            rank=ranks[str(t)]
            assert len(set(rank))==len(rank) and len(rank)<=8
            found=len(set(gold)&set(rank))
            hits+=found>0
            recalls.append(found/len(gold))
    return dict(n=len(recalls),recall_sum=sum(recalls),recall=mean(recalls),hits=hits)

def bootstrap(data,a,b):
    delta={repo:part[a]['recall']-part[b]['recall'] for repo,part in data.items()}
    rng=random.Random(SEED)
    draws=sorted(mean(rng.choices(list(delta.values()),k=len(delta))) for _ in range(20000))
    return dict(repo_delta=delta,macro_delta=mean(delta.values()),ci95=[draws[499],draws[19499]],
                wins=sum(x>1e-12 for x in delta.values()),losses=sum(x< -1e-12 for x in delta.values()))

def main(verify):
    fixed=io(HERE/'fixed-ranks.json.gz');layout=io(HERE/'layout-ranks.json.gz')
    files=io(HERE/'fixed-measurements.json.gz');bench=io(HERE/'layout-measurements.json.gz')
    output={}
    for panel,p in PANELS.items():
        raw=io(p/'commits.json.gz');projects={}
        for repo,stream in raw.items():
            rows,_=project(stream)
            both={**fixed[panel][repo],**layout[panel][repo]}
            projects[repo]={m:quality(r,rows) for m,r in both.items()}
        names=list(next(iter(projects.values())))
        table={}
        for m in names:
            s=[v[m] for v in projects.values()]
            n=sum(r['n'] for r in s)
            table[m]={'n':n,'recall':sum(r['recall_sum'] for r in s)/n,'hit':sum(r['hits'] for r in s),
                      'macro_recall':mean(r['recall'] for r in s)}
        for b in BUDGETS:
            for repo in raw:
                ns={files[panel][repo][m+str(b)]['compact_bytes'] for m in FIXED}
                assert len(ns)==1, (repo,b,ns)
            for m in FIXED:
                table[m+str(b)]['bytes']=sum(v[m+str(b)]['compact_bytes'] for v in files[panel].values())
                table[m+str(b)]['allocated_total_before_vacuum']=sum(v[m+str(b)]['file_bytes'] for v in files[panel].values())
        times=defaultdict(list)
        for block in bench:
            for m in LAYOUTS:
                records=[v for k,repo,method,v in block if k==panel and method==m]
                assert len(records)==len(raw)
                cold=sum(r['first_warm_ns'][3] for r in records)
                vals={k:sum(r[k] for r in records) for k in ('update_ns','query_ns','compact_bytes','file_bytes','changed_rows')}
                vals['fresh_read_us']=sum(r['first_warm_ns'][1] for r in records)/cold/1000
                vals['repeat_read_us']=sum(r['first_warm_ns'][2] for r in records)/cold/1000
                vals['open_us']=sum(r['first_warm_ns'][0] for r in records)/cold/1000
                times[m].append(vals)
        timings={m:{k:median(v[k] for v in vals) for k in vals[0]} for m,vals in times.items()}
        for a,b in [('pairs','log'),('shared','inline'),('intern','inline')]:
            assert all(layout[panel][proj][a]==layout[panel][proj][b] for proj in raw)
        output[panel]=dict(projects=projects,qualities=table,times_median_over_blocks=timings,
                        contrasts={a+'-'+b:bootstrap(projects,a,b) for a,b in [
                            ('runs64','skip64'),('skip64','raw64'),('runs64','space64'),
                            ('runs64','lossy64'),('runs64','pairs'),('space64','pairs')]})
    if verify: assert output==io(HERE/'results.json')
    else:io(HERE/'results.json',output)
    for panel,d in output.items():
        print(panel,{k:[round(v['recall']*100,2),v['hit'],v.get('bytes')] for k,v in d['qualities'].items()})
        print('physical',d['times_median_over_blocks'])
        print('contrasts',{k:[round(100*v['macro_delta'],2),[round(x*100,2) for x in v['ci95']],v['wins'],v['losses']] for k,v in d['contrasts'].items()})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true')
    main(p.parse_args().verify)

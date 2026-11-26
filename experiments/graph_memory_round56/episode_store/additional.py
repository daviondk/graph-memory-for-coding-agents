"""Paired rerun of all nine physical views with more compact exact comparators."""
import argparse
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
import random
from statistics import median
import tempfile
from bench import HERE,PANELS,LAYOUTS,SEED,execute,io,project
from extra_store import EXTRA

def run(scratch):
    corp={k:{repo:project(s) for repo,s in io(p/'commits.json.gz').items()} for k,p in PANELS.items()}
    original=io(HERE/'layout-ranks.json.gz')
    rng=random.Random(SEED+2)
    result=[]
    first=None
    with tempfile.TemporaryDirectory(dir=scratch,prefix='r56-compact-pairing-') as folder:
        for block in range(5):
            roster=[(k,repo,m) for k,repos in corp.items() for repo in repos for m in (*LAYOUTS,*EXTRA)]
            rng.shuffle(roster)
            data=[]
            for k,repo,m in roster:
                path=Path(folder)/'run.sqlite'
                ranks,metrics=execute(path,repo,*corp[k][repo],m,0,block,False)
                matched='log' if m in ('pairs','log','undirected','packedlog','pairblob') else 'inline'
                assert ranks=={int(t):tuple(v) for t,v in original[k][repo][matched].items()}
                if k=='external' and repo=='pallets/flask' and m=='packed8' and block==0:
                    import shutil
                    shutil.copyfile(path,HERE/'example-flask-packed.sqlite')
                path.unlink()
                data.append([k,repo,m,metrics])
            result.append(data)
            print('expanded',block+1,len(data),flush=True)
    io(HERE/'packed-measurements.json.gz',result)
    return result

def measure(records):
    result={}
    for k in PANELS:
        table={}
        for mode in (*LAYOUTS,*EXTRA):
            samples=[]
            for block in records:
                rows=[r for name,repo,m,r in block if name==k and m==mode]
                assert len(rows)==6
                totals={z:sum(r[z] for r in rows) for z in ('compact_bytes','file_bytes','changed_rows','update_ns','query_ns')}
                num=sum(r['first_warm_ns'][3] for r in rows)
                totals['fresh_us']=sum(r['first_warm_ns'][1] for r in rows)/num/1000
                totals['repeat_us']=sum(r['first_warm_ns'][2] for r in rows)/num/1000
                samples.append(totals)
            table[mode]={key:median(sample[key] for sample in samples) for key in samples[0]}
        result[k]=table
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true')
    p.add_argument('--scratch',type=Path,default=Path('D:/CodexResearch'))
    args=p.parse_args()
    r=measure(io(HERE/'packed-measurements.json.gz') if args.verify else run(args.scratch))
    if args.verify:assert r==io(HERE/'packed-results.json')
    else:io(HERE/'packed-results.json',r)
    for k,t in r.items():
        print(k,[(m,g['compact_bytes'],round(g['update_ns']/1e6,1),round(g['query_ns']/1e6,1)) for m,g in t.items()])

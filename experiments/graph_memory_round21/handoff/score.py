"""Open gold only after checking the sealed forecast file. Bootstrap whole articles."""
import argparse
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent

def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def contrast(rows,method,comparator,clusters):
    diff=[]; wins=losses=0
    for k in sorted(rows):
        d=rows[k][method]['both']-rows[k][comparator]['both']
        diff.append((clusters[k],d)); wins+=int(d==1); losses+=int(d==-1)
    groups=defaultdict(list)
    for g,d in diff:
        groups[g].append(d)
    counts=np.asarray([len(groups[g]) for g in sorted(groups)])
    sums=np.asarray([sum(groups[g]) for g in sorted(groups)])
    rng=np.random.default_rng(2107)
    sample=rng.integers(0,len(groups),size=(10000,len(groups)))
    estimates=sums[sample].sum(axis=1)/counts[sample].sum(axis=1)
    return dict(wins=wins,losses=losses,delta_pp=100*(wins-losses)/len(rows),ci95_pp=(100*np.percentile(estimates,[2.5,97.5])).tolist())


def score(gold_file):
    out=ROOT/'forecasts.jsonl.gz'
    seal=json.loads((ROOT/'forecast-lock.json').read_text())
    inputs=json.loads((ROOT/'input-lock.json').read_text())
    assert seal['forecast']==h(out) and seal['protocol']==h(ROOT/'protocol.json') and seal['selector']==h(ROOT/'predict.py')
    assert inputs['evaluator_sha']==h(gold_file)
    gold={r['case']:r for r in json.loads(gold_file.read_text(encoding='utf8'))}
    nested=defaultdict(lambda:defaultdict(dict))
    with gzip.open(out,'rt',encoding='utf8') as f:
        for line in f:
            r=json.loads(line)
            case=gold[r['case']]
            if len(set(case['gold'])) != 2:
                continue
            hit=[target in ids for target,ids in zip(case['gold'],r['ids'])]
            base=dict(both=int(all(hit)),endpoints=sum(hit),bytes=r['used'],frames=sum(map(len,r['ids'])))
            group='different' if case['different'] else 'same_distinct'
            for key in [group,'all_distinct',group+('_explicit' if case['explicit'] else '_implicit')]:
                nested[(key,r['budget'],r['limit'])][r['case']][r['method']]=base
    output={}
    for (group,b,lim),cases in sorted(nested.items()):
        methods=list(next(iter(cases.values())))
        n=len(cases)
        desc={}
        subsets={}
        for m in methods:
            rr=[v[m] for v in cases.values()]
            desc[m]=dict(pair=sum(r['both'] for r in rr),endpoint=sum(r['endpoints'] for r in rr),mean_frame=np.mean([r['frames'] for r in rr]),mean_byte=np.mean([r['bytes'] for r in rr]))
            for baseline in ('dense','dense_with_synopsis','shuffled'):
                if m=='paired':
                    subsets[m+' minus '+baseline]=contrast(cases,m,baseline,{k:v['article'] for k,v in gold.items()})
        output[f'{group}|{b}|{lim}']=dict(n=n,articles=len({gold[k]['article'] for k in cases}),metrics=desc,comparisons=subsets)
    (ROOT/'results.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(output['different|1536|fill'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--gold',type=Path,default=Path('D:/CodexResearch/x20-wikicontradict/gold.json'))
    args=p.parse_args()
    score(args.gold)


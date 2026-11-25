"""Test event-based marginal penalties on sealed native and factorized retrieval ranks."""
from collections import defaultdict
from pathlib import Path
import argparse
import heapq
import hashlib
import sys
import numpy as np
import analyze as a

HERE=a.HERE
ROOT=a.ROOT
TRAIN=ROOT.parent.parent/'graph_memory_round19/trained_rank'
FACTOR=ROOT.parent/'factor_reader'
sys.path.insert(0,str(ROOT/'cpu_fallback'))
import arithmetic as spans

TAGS=('dense','availability','hash64','full','degree_availability','degree_hash64')
METHODS=('skip','diverse','sham','concentrate')
METRICS=('full_support','coverage','tokens','events')
CONTRASTS=(('diverse','skip'),('diverse','sham'),('concentrate','skip'))

def orig_seal(tag):
    if tag=='dense':
        return TRAIN/'forecast-seal.json'
    if tag.startswith('degree_'):
        return FACTOR/(tag[7:]+'-seal.json')
    return (ROOT if tag=='full' else ROOT/'cpu_fallback'/tag)/'forecast-seal.json'

def inputs(tag):
    p=orig_seal(tag)
    return {'primary':a.sha(p),'dense_rank':a.sha(TRAIN/'forecast-seal.json')}

def lock():
    path=HERE/'diversity-plan.json'
    assert not path.exists()
    a.put(path,{'code':a.sha(HERE/'diversify.py'),'method':a.sha(HERE/'DIVERSITY_RU.md'),
                'upstream_at_design':{tag:inputs(tag) for tag in TAGS if orig_seal(tag).exists()},
                'old_flow':a.sha(HERE/'plan.json'),'n':2000,'budget':2048,'seed':260925,'boot':10000,'tags':TAGS})

def source(tag):
    seal=a.read(orig_seal(tag))
    if tag.startswith('degree_'):
        for part in range(8):
            name=f'forecasts-main-{part}.json.gz'
            assert a.sha(TRAIN/name)==a.read(TRAIN/'forecast-seal.json')['forecasts'][name]
            originals={rec['q']:rec for rec in a.read(TRAIN/name)}
            p=FACTOR/f'{tag[7:]}-ranks-{part}.json.gz'
            assert a.sha(p)==seal['files'][p.name]
            for rec in a.read(p):
                raw=originals[rec['q']]
                assert raw['t']==rec['t']
                indices=rec['ranks']['degree']
                assert sorted(indices)==list(range(len(raw['rr'])))
                yield rec['q'],rec['t'],[raw['rr'][i] for i in indices],None
        return
    prefix='forecasts-main-' if tag=='dense' else 'forecasts-rgcn-'
    files=seal['files'] if 'files' in seal else seal['forecasts']
    paths=[(p,sig) for p,sig in sorted(files.items()) if p.startswith(prefix)]
    assert len(paths)==8
    for name,sig in paths:
        p=orig_seal(tag).parent/name
        assert a.sha(p)==sig
        for raw in a.read(p):
            yield raw['q'],raw['t'],raw['rr'],raw['arms']['skip']

def geometry(rr,t):
    real=[]
    bins=defaultdict(list)
    for i,r in enumerate(rr):
        events={s['event_id'] for s in r['source_spans']}
        assert len(events)==1 and r['token_count']>0
        e=events.pop();real.append(e)
        n=r['token_count']
        bins[(n>64)+(n>256)+(n>504)].append(i)
    # Permute labels independently of caller ordering and method using node identity.
    fake=real.copy()
    for group in bins.values():
        orig=sorted(group,key=lambda i:rr[i]['node_id'])
        perm=sorted(group,key=lambda i:hashlib.sha256(('R20 event shuffle|'+t+'|'+rr[i]['node_id']).encode()).digest())
        for dest,src in zip(orig,perm,strict=True):
            fake[dest]=real[src]
        assert sorted(fake[i] for i in orig)==sorted(real[i] for i in orig)
    return real,fake

def pack(rr,group,method):
    by=defaultdict(list)
    for i,g in enumerate(group):
        by[g].append(i)
    heap=[(ids[0]+1,ids[0],g,0,0) for g,ids in by.items()]
    heapq.heapify(heap)
    result=[];left=2048
    while heap and left:
        _,idx,g,offset,k=heapq.heappop(heap)
        if rr[idx]['token_count']<=left:
            result.append(idx);left-=rr[idx]['token_count'];k+=1
        offset+=1
        if offset<len(by[g]):
            idx=by[g][offset]
            if method=='skip':
                weight=1
            elif method=='concentrate':
                weight=2/(2+k)
            else:
                weight=(2+k)/2
            heapq.heappush(heap,((idx+1)*weight,idx,g,offset,k))
    return result

def predict(tag):
    plan=a.read(HERE/'diversity-plan.json')
    assert plan['code']==a.sha(HERE/'diversify.py') and plan['method']==a.sha(HERE/'DIVERSITY_RU.md')
    src=inputs(tag)
    if tag in plan['upstream_at_design']:
        assert src==plan['upstream_at_design'][tag]
    rows=[]
    for q,t,rr,baseline in source(tag):
        real,sham=geometry(rr,t)
        all_methods={m:pack(rr,sham if m=='sham' else real,m) for m in METHODS}
        if baseline is not None:
            assert [rr[i]['node_id'] for i in all_methods['skip']]==baseline
        rows.append(dict(q=q,t=t,selections=all_methods,real_sham_changed=sum(x!=y for x,y in zip(real,sham,strict=True))))
    assert len({r['q'] for r in rows})==len(rows)==2000
    dest=HERE/f'diversity-{tag}-selections.json.gz'
    a.put(dest,rows)
    a.put(HERE/f'diversity-{tag}-seal.json',{'policy':a.sha(HERE/'diversity-plan.json'),'pred':a.sha(dest),'source':src})

def summaries(rows, seed, group, names):
    by=defaultdict(list)
    for r in rows:
        by[r['t']].append([[r['measures'][m][n] for n in names] for m in METHODS])
    ranked=sorted(by)
    arr=np.stack([np.sum(by[t],axis=0) for t in ranked])
    denom=np.array([len(by[t]) for t in ranked])
    values=arr.sum(axis=0)/denom.sum()
    sims=[]
    rng=np.random.default_rng(seed)
    for i in range(0,10000,64):
        ix=rng.integers(0,len(by),(min(64,10000-i),len(by)))
        sims.append(arr[ix].sum(axis=1)/denom[ix].sum(axis=1)[:,None,None])
    sims=np.concatenate(sims)
    paired={}
    for m,b in CONTRASTS:
        i,j=METHODS.index(m),METHODS.index(b)
        dif=sims[:,i]-sims[:,j]
        ci=np.quantile(dif,[.025,.975],axis=0)
        paired[m+' minus '+b]={k:{'difference':float(values[i,s]-values[j,s]),'ci95':ci[:,s].tolist()} for s,k in enumerate(names)}
    return {'n':len(rows),'tr':len(by),'methods':{m:dict(zip(names,x.tolist(),strict=True)) for m,x in zip(METHODS,values,strict=True)},'contrasts':paired}

def score(tag):
    sf=HERE/f'diversity-{tag}-seal.json'
    seal=a.read(sf)
    pf=HERE/f'diversity-{tag}-selections.json.gz'
    assert seal['source']==inputs(tag) and seal['pred']==a.sha(pf)
    rawg=a.read(a.GOLD);gold={q:a.by_field(s) for q,s in rawg.items()}
    selections={r['q']:r for r in a.read(pf)};out=[]
    for q,t,rr,_ in source(tag):
        pred=selections[q]
        assert pred['t']==t
        m=len({e for e,_ in gold[q]})
        row=dict(q=q,t=t,m=m,measures={})
        for alg,idx in pred['selections'].items():
            assert len(idx)==len(set(idx))
            selected=[rr[i] for i in idx]
            k=a.count_complete(gold[q],selected)
            v=spans.metric(spans.merged(rawg[q]),selected)
            assert (k==m)==bool(v['full_support']) and v['tokens']<=2048
            z=dict(full_support=int(k==m),coverage=v['coverage'],tokens=v['tokens'],
                events=len({s['event_id'] for item in selected for s in item['source_spans']}),
                event=k/m,pair=k*(k-1)/(m*(m-1)) if m>1 else None)
            row['measures'][alg]=z
        out.append(row)
    assert len(out)==2000 and len({r['q'] for r in out})==2000
    result={'seal':a.sha(sf),'gold':a.sha(a.GOLD),'panels':{}}
    for name,rows in [('all',out),('multiple',[r for r in out if r['m']>=2])]:
        measures=METRICS if name=='all' else METRICS+('event','pair')
        result['panels'][name]=summaries(rows,260925,name,measures)
    of=HERE/f'diversity-{tag}-outcomes.json.gz';a.put(of,out)
    result['outcomes']=a.sha(of)
    a.put(HERE/f'diversity-{tag}-score.json',result)
    print(tag,result['panels']['all']['contrasts']['diverse minus skip'],flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('stage',choices=['lock','predict','score'])
    ap.add_argument('tag',choices=TAGS,nargs='?')
    args=ap.parse_args()
    if args.stage=='lock':
        lock()
    else:
        assert args.tag
        {'predict':predict,'score':score}[args.stage](args.tag)

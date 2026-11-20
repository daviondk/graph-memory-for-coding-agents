"""Offline trust chain: source -> original/projection -> predicted memories -> per-record scores -> macro effects.
No credentials or nonstandard module required unless --tokens is supplied. No output files are modified.
"""
import argparse
import csv
import json
from collections import defaultdict
from itertools import zip_longest
from math import isclose
from statistics import mean
from followup_score import make_future,check
from score import ROOT,digest,load,readgz
from predict import author

def csv_map(file,labels):
    with (ROOT/file).open(encoding='utf8') as f:
        table=list(csv.DictReader(f))
    key=lambda r:tuple(str(r[k]) for k in labels)
    idx={key(r):r for r in table}
    assert len(table)==len(idx)
    return idx

def main(native):
    for manifest in ['source_manifest.json','followup_source.json']:
        for name,entry in load(manifest).items():assert digest(ROOT/'source'/name)==entry['sha256'],name
    if (ROOT/'checksum_manifest.json').exists():
        for name,h in load('checksum_manifest.json').items():assert digest(ROOT/name)==h,name
    lock=load('prediction_lock.json')
    assert digest(ROOT/'predictions.jsonl.gz')==lock['predictions_sha256']
    for n,h in lock['inputs'].items():assert digest(ROOT/n)==h,n
    for n in ['token_lock.json','e3_lock.json','robust_e2_lock.json','robust_e3_lock.json']:check(n)
    labels=list(readgz('gold.jsonl.gz'))
    author_strings={}
    with (ROOT/'source/sessions.jsonl').open(encoding='utf8') as f:
        for i,(ln,projection,gold) in enumerate(zip_longest(f,readgz('histories.jsonl.gz'),labels)):
            orig=json.loads(ln)
            assert projection=={'i':i,'H':orig['H']}
            assert all(orig[k]==v for k,v in gold.items())
            author_strings[i]=author.anchor_baseline(orig['H'])
    assert len(author_strings)==146
    chain_gold={};chain_src={}
    with (ROOT/'source/chains.jsonl').open(encoding='utf8') as f:
        for i,ln in enumerate(f):
            ch=json.loads(ln)
            assert [s['k'] for s in ch['per_k']]==sorted(set(s['k'] for s in ch['per_k']))
            for j,s in enumerate(ch['per_k']):
                chain_gold[i,j]=[(t,v) for t,vs in s['atomsF'].items() for v in vs]
                chain_src[i,j]=s['S_k']
    assert len(chain_gold)==224
    future,coverage=make_future()
    assert json.loads(json.dumps(future))==load('future_ground_truth.json')
    assert dict(coverage)==load('token_results.json')['coverage']
    pred_layout=[
        ('predictions.jsonl.gz','casewise.csv',['i','budget','arm']),
        ('token_predictions.jsonl.gz','token_casewise.csv',['i','endpoint','cost','arm']),
        ('e3_predictions.jsonl.gz','e3_casewise.csv',['i','j','arm']),
        ('robust_e2.jsonl.gz','robust_future_casewise.csv',['i','arm']),
        ('robust_e3.jsonl.gz','robust_e3_casewise.csv',['i','j','arm'])]
    official={i:[(a['kind'],a['value']) for a in g['atoms']] for i,g in enumerate(labels)}
    metrics=defaultdict(list);ns={}
    if native:
        from token_predict import token_count
    for filename,results,keynames in pred_layout:
        rows=csv_map(results,keynames)
        keys=set()
        for r in readgz(filename):
            i=r['i']; s=r['S']; a=r['arm']
            key=tuple(str(r[k]) for k in keynames)
            row=rows[key];assert key not in keys
            keys.add(key)
            if 'j' in r:
                j=r['j']; pairs=chain_gold[i,j]
                if a=='production':assert s==chain_src[i,j]
            elif filename=='robust_e2.jsonl.gz' or r.get('endpoint')=='future':
                pairs=future[i]
            else:pairs=official[i]
            if 'budget' in r:
                assert len(s)<=r['cap']
                if r['budget']=='natural' and a=='author_index':assert s==author_strings[i]
            if 'used' in r:
                cap=r.get('cap',r.get('base'))
                if a=='sidecar_extra':cap+=cap//10
                assert r['used']<=cap
                if r.get('cost')=='byte':assert r['used']==len(s.encode())
                elif native:assert r['used']==token_count(s)
                if native and 'tokens' in r:assert r['tokens']==token_count(s)
            hits=sum(v in s for t,v in pairs)
            assert hits==int(row['hits']),key
            assert len(pairs)==int(row.get('total',row.get('n')))
            if r.get('items') is not None:
                exact=set(map(tuple,r['items']))
                tc=row.get('typed_hits',row.get('typed'))
                if tc is not None:assert sum((t,v) in exact for t,v in pairs)==int(tc)
            if pairs:metrics[filename,r.get('budget',r.get('endpoint','')),r.get('cost',''),a, bool(r.get('j',0))].append(hits/len(pairs))
        ns[filename]=len(keys)
        if not filename.startswith('robust'):assert len(keys)==len(rows)
    assert list(ns.values())==[3942,3066,1120,438,354],ns
    E2=load('results.json')['budgets'];T=load('token_results.json')['summaries'];E3=load('e3_results.json')['summaries'];R=load('robust_results.json')
    checks=0
    for (name,b,c,a,later),vals in metrics.items():
        if name=='predictions.jsonl.gz':expected=E2[b]['methods'][a]['macro_recall']
        elif name=='token_predictions.jsonl.gz':expected=T[b+'|'+c][a]['macro']
        elif name=='e3_predictions.jsonl.gz':expected=E3['later' if later else 'first'][a]['macro_boundary']
        elif name=='robust_e2.jsonl.gz':expected=R['future'][a]['frequency']['macro']
        else:expected=R['chains']['comparisons'][a]['production']['macro']
        assert isclose(mean(vals),expected,abs_tol=1e-12)
        checks+=1
    print('OK',ns,'joined rows total',sum(ns.values()),'aggregate cells',checks,'native recount',native)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--tokens',action='store_true',help='also recount every frozen output with public Qwen tokenizer')
    main(p.parse_args().tokens)


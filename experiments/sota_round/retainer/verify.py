"""Independent arithmetic, exhaustive finite checks, on-disk hashes and model identity."""
from pathlib import Path
from itertools import combinations
from collections import Counter
import gzip
import hashlib
import json
import random
import re
import numpy as np
from study import HERE,RESULTS,group_stats,joint_mask_curves,joint_sets

def sha(b):return hashlib.sha256(b).hexdigest()
def load(name):return json.loads((HERE/name).read_text(encoding="utf8"))
def verify_freezes():
    amend=load('amendment.json')
    for name in ['freeze.json','native_freeze.json','week_freeze.json']:
        for rel,old in load(name)['sha256'].items():
            actual=sha((HERE/rel).read_bytes())
            if rel==amend['file']:
                assert old==amend['original_sha256'];assert actual==amend['amended_sha256']
            else:assert old==actual,rel
    for f,src in load('sources.json')['upstream'].items():
        assert sha((HERE/'upstream'/f).read_bytes())==src['sha256']

def values(a):
    return {'n':len(a),'page_misses':int(sum(a[:,1],start=np.uint64(0))),'underlying_reads':int(sum(a[:,0],start=np.uint64(0))),'page_accesses':int(sum(a[:,2],start=np.uint64(0))),'all_hit':int(np.count_nonzero(a[:,1]==0)),'within_one':int(np.count_nonzero(a[:,0]<=1))}

def entries(rows):
    seen={}
    for r in rows:
        key=r.get('row_sha256') or r['step_log']
        if key not in seen:
            b=gzip.decompress((RESULTS/'steps'/(key+'.gz')).read_bytes());assert sha(b)==key
            a=np.frombuffer(b,'<u4').reshape(-1,3)
            assert np.all(a[:,0]<=a[:,1]) and np.all(a[:,1]<=a[:,2]) and np.all(a[:,2]>0)
            assert np.all((a[:,1]==0)==(a[:,0]==0))
            assert np.all(a[:,0]*4>=a[:,1]);seen[key]=values(a)
        assert all(r[k]==v for k,v in seen[key].items())
    return seen

def exhaustive():
    rng=random.Random(626513)
    for i in range(18):
        pages=12;cap=rng.randint(1,5)
        hist=[rng.sample(range(pages),rng.randint(1,5)) for _ in range(11)]
        _,obs=group_stats(hist)
        selected=joint_sets(joint_mask_curves(obs),[cap])[cap]
        def cost(pinned):return sum(len({a//4 for a in job if a not in pinned}) for job in hist)
        optimum=min(cost(set(c)) for c in combinations(range(pages),cap))
        assert cost(selected)==optimum

def main():
    verify_freezes();exhaustive()
    servers=load('results/servers.json');rows=[r for s in servers for r in s['scores']]
    s4=load('results/range_s4.json')
    week=load('results/whole_week.json')
    unique=entries(rows+s4+week['methods'])
    nat=load('results/native.json')
    for m in nat['methods']:
        bits=gzip.decompress((RESULTS/('native_'+m['algo']+'.bits.gz')).read_bytes())
        a=np.unpackbits(np.frombuffer(bits,dtype='u1'),bitorder='little')[:m['n']]
        assert len(a)==m['n'] and int(a.sum())==m['page_misses']
        if 'bit_sha256' in m:assert sha(bits)==m['bit_sha256']
    lru=[m for m in nat['methods'] if 'lru' in m['algo']]
    assert lru[0]['page_misses']==lru[1]['page_misses'] and lru[0]['prefix_misses']==lru[1]['prefix_misses']
    ref=next(m for m in nat['methods'] if m['algo']=='reference_s3_python')
    chosen=next(m for m in nat['methods'] if m['algo']=='selected_pinned')
    assert nat['selected_pin_slots']==0 and chosen['bit_sha256']==ref['bit_sha256']
    old=load('results/historical.json')
    for m in old['methods']:
        alias={'S3FIFO':'s3','ARC':'arc','LRU':'lru'}[m['algo']]
        bits=gzip.decompress((RESULTS/('historical_'+alias+'.bits.gz')).read_bytes())
        assert sha(bits)==m['bits_sha256']
        assert int(np.unpackbits(np.frombuffer(bits,'u1'),bitorder='little')[:m['post_n']].sum())==m['post_misses']
        assert f"{m['full_misses']/m['full_n']:.4f}"==old['author_results'][m['algo']]
    assert len(old['methods'])==3
    pri=load('results/summary.json')
    for agg in pri['means']:
        arr=[r for r in rows if r['cap']==agg['cap'] and r['policy']==agg['policy']]
        assert abs(sum(r['underlying_reads']/r['n'] for r in arr)/len(arr)-agg['reads_per_request'])<1e-10
    # No dependence assumption on the thousands of individual reads.
    extrows=[]
    for a in ['joint','marginal','s3fifo','joint_half','joint_selected']:
        d=[]
        for s in servers:
            method=next(r for r in s['scores'] if r['policy']==a and r['cap']==512)
            ext=next(r for r in s4 if r['volume']==s['volume'])
            d.append((ext['underlying_reads']-method['underlying_reads'])/method['n'])
        d=np.array(d)
        boot=np.random.default_rng(327816).choice(d,(10000,len(d))).mean(1)
        extrows.append(dict(candidate=a,ref='s4',reference_minus_candidate=d.mean(),ci=np.percentile(boot,[2.5,97.5]).tolist(),wins=int((d>0).sum()),ties=int((d==0).sum()),losses=int((d<0).sum())))
    out={'range_configurations':len(rows)+len(s4),'range_server_count':len(servers),'held_out_requests':sum(s['n_test'] for s in servers),'unique_logs_with_week':len(unique),'native_records':nat['records'],'matched_published_cells':len(old['methods']),'exhaustive_exact_optimum_checks':18,'native_nontrivial_predictions':int('valid=1 ' in nat['methods'][0]['run_log']),'range_nontrivial_predictions':sum('valid=1 ' in s['run_log'] for s in s4),'external_contrasts':extrows}
    (RESULTS/'verification.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print(json.dumps(out))
if __name__=='__main__':main()

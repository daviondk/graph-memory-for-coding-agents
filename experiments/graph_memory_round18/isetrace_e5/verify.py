"""Re-score each shipped forecast with standard-library interval algebra; archive-only."""
import collections,gzip,hashlib,json,math
from pathlib import Path
from statistics import mean
ROOT=Path(__file__).resolve().parent
OFF=ROOT.parent/'isetrace_official'
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def merged(spans):
    groups=collections.defaultdict(list)
    for s in spans:groups[s['event_id'],s['json_pointer']].append((s['char_start'],s['char_end']))
    result={}
    for f,ranges in groups.items():
        blocks=[]
        for lo,hi in sorted(ranges):
            if blocks and blocks[-1][1]>=lo:blocks[-1]=(blocks[-1][0],max(hi,blocks[-1][1]))
            else:blocks.append((lo,hi))
        result[f]=blocks
    return result
def measures(truth,nodes):
    spans=[s for n in nodes for s in n['source_spans']]
    p=merged(spans);g=merged(truth)
    total=sum(e-b for blocks in g.values() for b,e in blocks)
    readsize=sum(s['char_end']-s['char_start'] for s in spans)
    hit=sum(max(0,min(e,y)-max(b,x)) for f in g for b,e in g[f] for x,y in p.get(f,()))
    assert 0<=hit<=total
    cov=hit/total;den=hit/readsize if readsize else 0
    return dict(full_support=int(hit==total),coverage=cov,density=den,f1=2*cov*den/(cov+den) if cov+den else 0,tokens=sum(n['token_count'] for n in nodes),nodes=len(nodes))
def verify():
    for n,h in read(ROOT/'MANIFEST_SHA256.json').items():assert sha(ROOT/n)==h,n
    plan=read(ROOT/'plan-seal.json');assert all(sha(ROOT/n)==h for n,h in plan.items())
    seal=read(ROOT/'forecast-seal.json');assert sha(ROOT/'plan-seal.json')==seal['plan']
    assert all(sha(ROOT/n)==h for n,h in seal['forecasts'].items())
    gold=read(OFF/'gold-spans.json.gz');out={(r['group'],r['q'],r['arm']):r for r in read(ROOT/'outcomes.json.gz')}
    seen=set();means=collections.defaultdict(list)
    for file in seal['forecasts']:
        group='main' if '-main-' in file else 'audit-fp32'
        for r in read(ROOT/file):
            rr=r['rr'];lookup={n['node_id']:n for n in rr}
            assert len(lookup)==len(rr)
            if r['partial']:lookup[r['partial']['node_id']]=r['partial']
            p=r['arms']['prefix']
            assert p==[n['node_id'] for n in rr[:len(p)]]
            if len(p)<len(rr):assert sum(n['token_count'] for n in rr[:len(p)+1])>2048
            for arm,selection in r['arms'].items():
                assert len(selection)==len(set(selection)) and selection[:len(p)]==p
                result=measures(gold[r['q']],[lookup[k] for k in selection])
                key=group,r['q'],arm;assert key not in seen;seen.add(key)
                assert result['tokens']<=2048 and all(abs(v-out[key][m])<1e-12 for m,v in result.items()),key
                means[group,arm].append(result)
    assert seen==set(out) and len({q for group,q,_ in seen if group=='main'})==2000
    res=read(ROOT/'results.json')
    for (group,arm),rr in means.items():
        assert all(abs(mean(r[m] for r in rr)-res['groups'][group][arm][m])<1e-10 for m in rr[0])
    place=read(ROOT/'placebo-seal.json')
    assert place['official_forecast']==sha(ROOT/'forecast-seal.json') and all(sha(ROOT/n)==h for n,h in place['files'].items())
    for row in read(ROOT/'placebo-outcomes.json.gz'):
        actual=out['main',row['q'],'related']
        assert all(abs(v-actual[m])<1e-12 for m,v in row['actual'].items())
    grid=read(ROOT/'grid-seal.json'); assert grid['forecast']==sha(ROOT/'forecast-seal.json')
    assert all(sha(ROOT/n)==h for n,h in grid['files'].items())
    gr={(r['q'],r['arm'],r['b']):r for r in read(ROOT/'grid-outcomes.json.gz')}
    pl={(r['q'],r['mode']):r for r in read(ROOT/'placebo-outcomes.json.gz')}
    ng=np=0
    for i in range(8):
        gp=read(ROOT/f'grid-picks-{i}.json.gz');pp=read(ROOT/f'placebo-picks-{i}.json.gz')
        for r in read(ROOT/f'forecasts-main-{i}.json.gz'):
            q=r['q'];rank=r['rr'];prefix=list(range(len(r['arms']['prefix'])));cached={}
            def check_idx(ii):
                key=tuple(ii)
                if key not in cached:cached[key]=measures(gold[q],[rank[j] for j in ii])
                return cached[key]
            for budget,arms in gp[q].items():
                for arm,ids in arms.items():
                    x=gr[q,arm,int(budget)];ms=check_idx(ids)
                    assert ms['tokens']<=int(budget) and all(abs(x[m]-ms[m])<1e-12 for m in ['coverage','density','full_support','tokens'])
                    ng+=1
            for mode,draws in pp[q].items():
                expected=pl[q,mode];vals=[check_idx(prefix+ids) for ids in draws]
                assert expected['seeds_fs']==[v['full_support'] for v in vals]
                assert all(abs(mean(v[m] for v in vals)-x)<1e-12 for m,x in expected['placebo'].items());np+=len(vals)
    assert ng==len(gr)==48000 and np==64000
    print('checked',len(seen),'main outcomes,',ng,'grid cells,',np,'placebo policies on 2000 queries')
if __name__=='__main__':verify()

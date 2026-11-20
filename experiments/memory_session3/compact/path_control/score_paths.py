"""Offline scoring and verification. --verify compares the freshly computed report with recorded data, without writes."""
import csv,gzip,hashlib,json,sys
from pathlib import Path
from collections import Counter,defaultdict
from statistics import mean
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from score import ci

def lines(p):
    with gzip.open(p,'rt',encoding='utf8') as f:
        yield from map(json.loads,f)

def measure(verify):
    hashes=json.loads((ROOT/'lock.json').read_text())['sha256']
    for name,h in hashes.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
    inputs={(r['i'],r['j']):r for r in lines(ROOT/'prefixes.jsonl.gz')}
    with (ROOT.parent/'source/chains.jsonl').open(encoding='utf8') as src:
        raw={}
        for i,ln in enumerate(src):
            for j,b in enumerate(json.loads(ln)['per_k']):
                r=inputs[i,j];assert (r['summary'],r['writes'])==(b['S_k'],b['done_files'])
                raw[i,j]=b
    preds=list(lines(ROOT/'predictions.jsonl.gz'))
    assert len(preds)==590 and len({(r['i'],r['j'],r['arm']) for r in preds})==590
    preds.extend(r for r in lines(ROOT.parent/'e3_predictions.jsonl.gz') if r['j'] and r['arm'] in ['production','sidecar_fixed'])
    counts=defaultdict(Counter);rec=[]
    if '--tokens' in sys.argv:
        from token_predict import token_count
    for r in preds:
        key=r['i'],r['j']; assert r['used']<=r.get('cap',r.get('base'))
        if '--tokens' in sys.argv:assert r['used']==token_count(r['S'])
        pairs=[(k,v) for k,vs in raw[key]['atomsF'].items() for v in vs]
        hits=sum(v in r['S'] for k,v in pairs); a=r['arm']
        for k,v in pairs:
            counts[a,k].update({'n':1,'hits':int(v in r['S'])})
        rec.append({'arm':a,'i':key[0],'j':key[1],'n':len(pairs),'hits':hits,'used':r['used'],'extra_tokens':r.get('extra_tokens',r.get('available') if a=='sidecar_fixed' else 0)})
    stats={}
    for a in sorted({r['arm'] for r in rec}):
        all_r=[r for r in rec if r['arm']==a]; denom=[r for r in all_r if r['n']]
        def paired(ref):
            comp={(r['i'],r['j']):r for r in rec if r['arm']==ref}
            ds=[(r['hits']-comp[r['i'],r['j']]['hits'])/r['n'] for r in denom]
            groups=defaultdict(list)
            for r,d in zip(denom,ds):groups[r['i']].append(d)
            return {'delta':mean(ds),'ci':ci(groups),'W':sum(x>0 for x in ds),'L':sum(x<0 for x in ds),'T':ds.count(0)}
        stats[a]={'N':len(denom),'macro':mean(r['hits']/r['n'] for r in denom),'micro':sum(r['hits'] for r in denom)/sum(r['n'] for r in denom),'tokens':sum(r['used'] for r in all_r),'vs_production':paired('production'),'vs_write_paths':paired('write_paths'),'vs_paths':paired('paths')}
    out={'valid':len(denom),'arms':stats,'types':{'|'.join(k):v for k,v in counts.items()}}
    if verify:
        assert out==json.loads((ROOT/'results.json').read_text())
        with (ROOT/'casewise.csv').open(encoding='utf8') as f: assert list(csv.DictReader(f))==[{k:str(v) for k,v in r.items()} for r in rec]
    else:
        (ROOT/'results.json').write_text(json.dumps(out,indent=1),encoding='utf8')
        with (ROOT/'casewise.csv').open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rec[0]));w.writeheader();w.writerows(rec)
    print('Verified paired paths',len(preds),'rows')
if __name__=='__main__':measure('--verify' in sys.argv)


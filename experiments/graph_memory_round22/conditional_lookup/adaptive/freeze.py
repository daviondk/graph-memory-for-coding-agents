"""Freeze all observable features first, then export fold-excluded training labels."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

D = Path(__file__).resolve().parent
ROOT = D.parent
FEATURES = ["log_distance_hybrid1", "log_distance_hybrid2", "log_distance_neighbor2",
            "bm25_e5_same_first", "bm25_e5_same_second", "bm25_e5_common_top2_fraction"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    b=path.read_bytes()
    return json.loads(gzip.decompress(b) if path.suffix=='.gz' else b)


def dump(path, value):
    raw=(json.dumps(value,ensure_ascii=False,separators=(',',':'),sort_keys=True,allow_nan=False)+'\n').encode()
    encoded=gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw
    if path.exists(): assert path.read_bytes()==encoded, path
    else: path.write_bytes(encoded)


def census():
    f=ROOT/'forecasts.json.gz'
    assert digest(f)==read(ROOT/'forecast-lock.json')['forecast']
    base=read(f)
    groups=read(ROOT/'data-audit.json')['document_reuse']['map_jaccard90']
    def component(doc):
        key=hashlib.sha256(('contradoc-family-v1|'+doc.rsplit('_',1)[0]).encode('ascii')).hexdigest()[:16]
        return groups[key]
    hashes=sorted(set(groups.values()),key=lambda g:hashlib.sha256(('adaptive-lookup-22|'+g).encode()).digest())
    folds={g:j%5 for j,g in enumerate(hashes)}
    result=[]
    for r in sorted(base,key=lambda x:x['id']):
        p=r['picks']; bm=p['bm25'][:2];e=p['e5'][:2];hy=p['hybrid'][:2];near=p['neighbor'][:2]
        assert hy[0]==near[0] and len(set(hy))==len(set(near))==2
        x=[math.log10(1+abs(v)) for v in (hy[0],hy[1],near[1])]
        x += [int(bm[0]==e[0]),int(bm[1]==e[1]),len(set(bm)&set(e))/2]
        g=component(r['id'])
        result.append(dict(id=r['id'],comp=g,fold=folds[g],x=x,picks=dict(hybrid=hy,neighbor=near,bm25=bm)))
    assert len(result)==len({r['id'] for r in result})==449
    assert len(set(r['comp'] for r in result))==218
    dump(D/'features.json.gz',result)
    dump(D/'feature-lock.json',dict(plan=digest(D/'PLAN_RU.md'),code=digest(Path(__file__)),features=FEATURES,
         source_rank=digest(f),source_components=digest(ROOT/'data-audit.json'),fold_members=folds,inputs=digest(D/'features.json.gz')))


def training():
    feature=read(D/'feature-lock.json')
    assert feature['inputs']==digest(D/'features.json.gz') and feature['plan']==digest(D/'PLAN_RU.md')
    xs=read(D/'features.json.gz');old=read(ROOT/'outcomes.json.gz')
    receipt=read(ROOT/'results.json')
    assert digest(ROOT/'outcomes.json.gz')==receipt['outcomes']
    labels={r['id']:r['methods']['neighbor']['hit2']-r['methods']['hybrid']['hit2'] for r in old if r['reachable']}
    files={}
    for fold in range(5):
        ls=[{'id':r['id'],'y':int(labels[r['id']]>0)} for r in xs if r['fold']!=fold and labels.get(r['id'],0)!=0]
        assert not ({r['id'] for r in ls}&{r['id'] for r in xs if r['fold']==fold})
        dest=D/f'train-excluding-{fold}.json.gz'
        dump(dest,ls);files[dest.name]=digest(dest)
    dump(D/'training-lock.json',dict(files=files,feature_lock=digest(D/'feature-lock.json'),source_labels=digest(ROOT/'outcomes.json.gz')))


if __name__=='__main__': {'features':census,'training':training}[sys.argv[1]]()


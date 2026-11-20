"""Inspect the identities of ChainSWE sequences to choose a disjoint evaluation unit."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
REV='dcaa484eca5b38caca71420712b1b194c1235d6e'
ORIGIN='https://huggingface.co/datasets/C-lister/ChainSWE'
SPLITS=['len_3','len_4','len_5','unique']

def h(value):
    return hashlib.sha256(value).hexdigest()

def dump(p,v):
    b=json.dumps(v,sort_keys=True,separators=(',',':')).encode()
    if p.exists():
        existing=p.read_bytes()
        if p.suffix=='.gz':existing=gzip.decompress(existing)
        assert existing==b,p
        return
    if p.suffix=='.gz':
        b=gzip.compress(b,mtime=0)
    p.write_bytes(b)

def project():
    import pyarrow.parquet as pq
    import requests
    url='https://huggingface.co/api/datasets/C-lister/ChainSWE/tree/'+REV+'/data'
    res=requests.get(url,timeout=30)
    res.raise_for_status()
    expected={Path(r['path']).stem:r['lfs']['oid'] for r in res.json()}
    def one(s):
        response=requests.get(f'{ORIGIN}/resolve/{REV}/data/{s}.parquet',timeout=60)
        response.raise_for_status()
        assert h(response.content)==expected[s]
        f=pq.ParquetFile(io.BytesIO(response.content))
        rows=f.read(columns=['continuous_id','repo','base_commit','swebench_instance_ids','length']).to_pylist()
        return s,rows
    with ThreadPoolExecutor(4) as pool:
        data=dict(pool.map(one,SPLITS))
    dump(ROOT/'projection.json.gz',data)
    dump(ROOT/'sources.json',dict(revision=REV,official_tree=url,parquet_sha256=expected,projection=h((ROOT/'projection.json.gz').read_bytes())))

def ids(r):
    return [(r['repo'],s) if s and str(s).strip().lower() not in {'none','null','n/a','unknown'} else None for s in r['swebench_instance_ids']]

def edges(row):
    seq=ids(row)
    return [(a,b) for a,b in zip(seq,seq[1:]) if a and b]

def summary(rows):
    positions=[v for r in rows for v in ids(r)]
    return dict(rows=len(rows),unique_sequence_ids=len({r['continuous_id'] for r in rows}),repos=len({r['repo'] for r in rows}),declared_issue_positions=sum(r['length'] for r in rows),id_slots=len(positions),missing=sum(v is None for v in positions),distinct_scoped_issues=len(set(positions)-{None}),distinct_scoped_adjacent_pairs=len({v for r in rows for v in edges(r)}),distinct_ordered_issue_sequences=len({(r['repo'],tuple(ids(r))) for r in rows}))

def audit(rows,key):
    byrepo=Counter(r['repo'] for r in rows)
    blocks=sorted(byrepo,key=lambda b:(-byrepo[b],h(b.encode())))
    sizes=[0]*5;repofold={}
    for b in blocks:
        dest=min(range(5),key=lambda k:(sizes[k],k))
        repofold[b]=dest;sizes[dest]+=byrepo[b]
    ranked=sorted(rows,key=lambda r:h(('s6-chain|'+r['continuous_id']).encode()))
    folds=[repofold[r['repo']] if key=='repository' else i%5 for i,r in enumerate(ranked)]
    result=Counter();splitlog=[]
    for fold in range(5):
        train=[r for r,k in zip(ranked,folds) if k!=fold]
        test=[r for r,k in zip(ranked,folds) if k==fold]
        seen={v for r in train for v in ids(r) if v};past={v for r in train for v in edges(r)}
        for r in test:
            valid=[v for v in ids(r) if v]
            overlap=sum(v in seen for v in valid)
            result.update({'sequences':1,'any_issue_overlap':int(bool(overlap)),'all_positions':len(valid),'overlap_positions':overlap,'any_adjacent_overlap':int(any(v in past for v in edges(r)))})
            splitlog.append({'id':r['continuous_id'],'repo':r['repo'],'fold':fold,'positions':len(valid),'overlap':overlap})
    return dict(result),splitlog

def main():
    if '--fetch' in sys.argv:project()
    data=json.loads(gzip.decompress((ROOT/'projection.json.gz').read_bytes()))
    assert h((ROOT/'projection.json.gz').read_bytes())==json.loads((ROOT/'sources.json').read_bytes())['projection']
    vals={name:summary(rows) for name,rows in data.items()}
    vals['length_union']=summary([r for s in SPLITS[:3] for r in data[s]])
    diagnostics={};folds={}
    for k in ('sequence','repository'):
        diagnostics[k],folds[k]=audit(data['unique'],k)
    assert diagnostics['repository']['overlap_positions']==0
    result=dict(split=vals,diagnostics=diagnostics)
    dump(ROOT/'folds.json.gz',folds)
    dump(ROOT/'results.json',result)
    print(json.dumps(result,indent=1))

if __name__=='__main__':main()

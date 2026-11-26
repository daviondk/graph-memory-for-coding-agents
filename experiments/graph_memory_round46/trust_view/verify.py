import gzip, json, sqlite3, struct
from pathlib import Path
root=Path(__file__).resolve().parent
meta=json.loads((root/'view-log.json').read_bytes())
db=sqlite3.connect((root/'view.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)
assert db.execute('pragma integrity_check').fetchone()==('ok',)
assert not db.execute('pragma foreign_key_check').fetchall()
assert db.execute('select count(*) from edge').fetchone()==(meta['changes'],)
assert db.execute('select count(*) from packet').fetchone()==(meta['records'],)
queries={}
for q,s,lower,blob in db.execute('select q,source,start,members from edge join packet on id=packet_id order by q,source,start'):
    seq=queries.setdefault((q,s),[])
    if not seq:assert lower==-(1<<30)
    else:assert seq[-1][1]!=blob and seq[-1][0]<lower
    ids=struct.unpack('<'+'H'*(len(blob)//2),blob)
    assert len(set(ids))==len(ids) and lower<=1<<30
    seq.append((lower,blob))
assert len(queries)==2528 and meta['validated']==91748
ctl=json.loads((root/'control-results.json').read_bytes())
timings=json.loads(gzip.decompress((root/'control-times.json.gz').read_bytes()))
for s in ('new','repeated'):
    for arm,t in ctl[s]['mean_us'].items():
        subset=[(n,ns) for scen,rep,q,a,n,ns in timings if scen==s and a==arm]
        assert sum(n for n,_ in subset)==ctl[s]['per_mode']
        assert abs(sum(v for _,v in subset)/sum(n for n,_ in subset)/1000-t)<1e-9
print('Checked SQL structure, 5426 maximal intervals, all 1280 timing blocks and the number of reads.')

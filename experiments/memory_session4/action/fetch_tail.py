import urllib.request,hashlib,json
from pathlib import Path
P=Path(__file__).resolve().parent
name='restarted_logs.tail128.gz.part';p=P/name;start=64*1024**2;end=192*1024**2-1
url='https://zenodo.org/records/3601137/files/restarted_logs.bson.gz?x20=tail-validation'
if not p.exists():
    req=urllib.request.Request(url,headers={'Range':f'bytes={start}-{end}'})
    with urllib.request.urlopen(req,timeout=240) as r:
        assert r.status==206 and r.headers['Content-Range'].startswith(f'bytes {start}-{end}/')
        data=r.read()
    assert len(data)==end-start+1;p.write_bytes(data)
data=p.read_bytes()
(P/'tail_source.json').write_text(json.dumps({'name':name,'url':url,'range':[start,end],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},indent=1))
print('tail bytes saved')

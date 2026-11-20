from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,urllib.request
ROOT=Path(__file__).resolve().parent
def get(name):
    limit=64*1024**2 if name=='restarted_logs' else None
    url='https://zenodo.org/records/3601137/files/'+name+'.bson.gz?x20=phase4-20261117'
    file=ROOT/(name+('.prefix.gz.part' if limit else '.bson.gz'))
    req=urllib.request.Request(url,headers={'Range':'bytes=0-'+str(limit-1)} if limit else {})
    if not file.is_file():
        with urllib.request.urlopen(req,timeout=210) as r:
            if limit:assert r.status==206 and r.headers['Content-Range'].startswith('bytes 0-'+str(limit-1)+'/')
            data=r.read()
        if limit:assert len(data)==limit
        else:assert hashlib.md5(data).hexdigest()=='309a6e332fdf2c67e5e2a2fad99fbcd6'
        file.write_bytes(data)
    data=file.read_bytes()
    return file.name,{'url':url,'range':None if not limit else [0,limit-1],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'md5':hashlib.md5(data).hexdigest()}
if __name__=='__main__':
    with ThreadPoolExecutor(2) as ex:res=dict(ex.map(get,['restarted_jobs','restarted_logs']))
    (ROOT/'job_sources.json').write_text(json.dumps(res,indent=1));print(res)

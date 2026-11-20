"""Pin the full LFS file for reliable sequential access, then project only four metadata columns."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,requests,time
from pathlib import Path
from extract import D,get,save
from meta import URL
import pyarrow.parquet as pq
SIZE=428839266;EXPECTED='0e0bf9355f892ad74ae98d4e1c404f39fd6654a8e351ee3e6ab162e4a64cd3ad'
ROOT=Path('D:/CodexResearch/x20-round12-negative-objects');ROOT.mkdir(exist_ok=True)
def one(bounds):
    a,b=bounds;q=ROOT/f'parquet-{a}-{b}.part'
    if not q.exists() or q.stat().st_size!=b-a+1:
        for i in range(3):
            try:
                with requests.get(URL+'?block='+str(a),headers={'Range':f'bytes={a}-{b}'},stream=True,timeout=(15,60)) as r:
                    r.raise_for_status();assert r.status_code==206 and r.headers['Content-Range'].startswith(f'bytes {a}-{b}/')
                    with q.open('wb') as f:
                        for chunk in r.iter_content(1024*1024):f.write(chunk)
                assert q.stat().st_size==b-a+1;break
            except (OSError,AssertionError,requests.RequestException):
                if i==2:raise
    return q
if __name__=='__main__':
    local=ROOT/'SWE-rebench-V2.parquet'
    if not local.is_file():
        stride=16*1024**2
        parts=[(a,min(SIZE,a+stride)-1) for a in range(0,SIZE,stride)]
        with ThreadPoolExecutor(8) as p:filenames=list(p.map(one,parts))
        stage=ROOT/'SWE-rebench-V2.staged'
        with stage.open('wb') as out:
            for f in filenames:
                with f.open('rb') as src:
                    while block:=src.read(2**20):out.write(block)
        with stage.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==EXPECTED
        os.replace(stage,local)
        for p in filenames:p.unlink()
    t=pq.read_table(local,columns=['instance_id','repo','created_at','base_commit']).to_pylist()
    selected={r['iid'] for r in get(D/'roster.json')}
    save('task_meta_panel.json',{r['instance_id']:r for r in t if r['instance_id'] in selected})
    save('metadata_receipt.json',{'url':URL,'sha':EXPECTED,'columns':['instance_id','repo','created_at','base_commit'],'total':len(t),'retained':len(get(D/'task_meta_panel.json'))})
    print(get(D/'metadata_receipt.json'))

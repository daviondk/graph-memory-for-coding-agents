"""Capture pinned parquet bytes, then retain complete chronological public tool observations for hash-selected issues."""
from pathlib import Path
import gzip,hashlib,json,os,sys,time
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.scratch/lib'))
import requests
import pyarrow.parquet as pq
REV='08e109b4a59eaeebf80e4675cd125d42e7ac99a4'
ID='SWE-bench/SWE-smith-trajectories'
EXCLUDE='django-money__django-money.835c1ab8.func_pm_ctrl_shuffle__viqnyl9u'
def dump(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'))
def sha(x):return hashlib.sha256(x).hexdigest()
def textparts(content):
    if isinstance(content,str):return content
    return '\n'.join(i.get('text','') for i in content or [] if isinstance(i,dict))
def convert(row,shard,i):
    ms=json.loads(row['messages']);events=[];calls={};track={}
    for m in ms:
        role=m.get('role')
        if role=='assistant':
            for c in (m.get('tool_calls') or []):
                cid=c.get('id');f=c.get('function',{});args=f.get('arguments') or '{}'
                try:args=json.loads(args) if isinstance(args,str) else args
                except (ValueError,TypeError):args={}
                calls[cid]=(f.get('name'),args)
        elif role=='tool':
            ids=m.get('tool_call_ids') or [m.get('tool_call_id')]
            if len(ids)==1 and ids[0] in calls: name,args=calls.pop(ids[0])
            else: name,args='unresolved',{}
            events.append([name,args,textparts(m.get('content'))])
    return {'shard':shard,'row':i,'instance':row['instance_id'],'traj':row['traj_id'],'model':row['model'],'issue':next((textparts(m.get('content')) for m in ms if m.get('role')=='user'),''),'events':events,'messages_sha':sha(row['messages'].encode())}
def fetch(item):
    path=item['path'];k=int(path.split('tool-')[1][:5]);dest=ROOT/'source'/f'{k}.jsonl.gz';stat=ROOT/'source'/f'{k}-metadata.json'
    if stat.is_file() and dest.is_file():return
    tmp=ROOT/'.scratch'/Path(path).name;tmp.parent.mkdir(exist_ok=True)
    url=f'https://huggingface.co/datasets/{ID}/resolve/{REV}/{path}'
    if not tmp.is_file() or tmp.stat().st_size!=item['size']:
        with requests.get(url,params={'download':'true','round':str(time.time_ns())},stream=True,timeout=(15,100)) as resp:
            resp.raise_for_status()
            with tmp.open('wb') as f:
                for b in resp.iter_content(2**20):f.write(b)
    dg=hashlib.sha256()
    with tmp.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):dg.update(b)
    assert dg.hexdigest()==item['lfs']['oid']
    pf=pq.ParquetFile(tmp);idx=0;n=0;dest.parent.mkdir(exist_ok=True)
    with gzip.open(dest.with_suffix('.tmp'),'wt',encoding='utf8') as out:
        for batch in pf.iter_batches(batch_size=24,columns=['messages','instance_id','model','traj_id'],use_threads=False):
            for row in batch.to_pylist():
                if row['instance_id']!=EXCLUDE and int(sha(('compact-s4|'+row['instance_id']).encode()),16)%10==0:
                    print(dump(convert(row,k,idx)),file=out);n+=1
                idx+=1
    pf.close()
    dest.with_suffix('.tmp').replace(dest)
    stat.write_text(json.dumps({'shard':path,'url':url,'sha256':dg.hexdigest(),'rows':idx,'kept':n,'source_bytes':item['size'],'projection_sha256':sha(dest.read_bytes())},indent=1))
    print(k,idx,n,flush=True)
    assert tmp.resolve().is_relative_to((ROOT/'.scratch').resolve());tmp.unlink()
if __name__=='__main__':
    (ROOT/'source').mkdir(exist_ok=True)
    api=f'https://huggingface.co/api/datasets/{ID}/tree/{REV}/data?limit=100'
    items=[i for i in requests.get(api,timeout=25).json() if '/tool-' in i['path']];assert len(items)==8
    (ROOT/'source'/'shards.json').write_text(json.dumps(items,indent=1))
    with ThreadPoolExecutor(3) as pool:list(pool.map(fetch,items))


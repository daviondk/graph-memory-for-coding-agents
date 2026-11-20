"""Project the author's second, tagged message format. All memory policies and scorers remain identical."""
from pathlib import Path
import gzip,hashlib,json,os,re,shutil,sys
import collect as base
import pyarrow.parquet as pq
import requests
R=base.ROOT;T=R/'tagged'
def wrapper(x):
    if x.startswith('\n'):x=x[1:]
    if x.endswith('\n'):x=x[:-1]
    return x
def one(row,k,i,ms):
    events=[];prev=None
    for m in ms:
        if m['role']=='assistant':
            text=base.textparts(m.get('content'))
            fs=list(re.finditer(r'<function=([\w.-]+)>(.*?)</function>',text,re.S))
            if len(fs)==1:
                name,body=fs[0].groups()
                a={k:wrapper(v) for k,v in re.findall(r'<parameter=([\w.-]+)>(.*?)</parameter>',body,re.S)}
                if 'view_range' in a:
                    try:a['view_range']=json.loads(a['view_range'])
                    except ValueError:pass
                prev=[name,a]
            else:prev=['unresolved',{}]
        if m['role']=='user' and prev is not None:
            events.append([*prev,base.textparts(m.get('content'))]);prev=None
    return {'shard':k,'row':i,'instance':row['instance_id'],'traj':row['traj_id'],'model':row['model'],'issue':next((base.textparts(m.get('content')) for m in ms if m.get('role')=='user'),''),'events':events,'messages_sha':base.sha(row['messages'].encode())}
def main():
    (T/'source').mkdir(parents=True,exist_ok=True)
    for name in ['collect.py','common.py','predict.py','score.py','PROTOCOL.md','WRITE_AMENDMENT.md','TAGGED_PROTOCOL.md','tagged_extract.py']:
        shutil.copy2(R/name,T/name)
    shutil.copy2(R/'source/qwen_tokenizer.json',T/'source/qwen_tokenizer.json')
    metadata=json.loads((R/'source/shards.json').read_bytes())
    counts={}
    for k,item in enumerate(metadata):
        path=item['path'];tmp=R/'.scratch'/Path(path).name
        if not tmp.exists():
            url=f'https://huggingface.co/datasets/{base.ID}/resolve/{base.REV}/{path}?download=true'
            with requests.get(url,stream=True,timeout=120) as resp:
                resp.raise_for_status()
                with tmp.open('wb') as f:
                    for b in resp.iter_content(1048576):f.write(b)
        assert base.sha(tmp.read_bytes())==item['lfs']['oid']
        pf=pq.ParquetFile(tmp);nr=0;included=0
        forbidden={'django-money__django-money.835c1ab8.func_pm_ctrl_shuffle__viqnyl9u'}
        with gzip.open(T/'source'/f'{k}.jsonl.gz','wt',encoding='utf8') as f:
            for batch in pf.iter_batches(batch_size=24,columns=['messages','instance_id','model','traj_id'],use_threads=False):
                for row in batch.to_pylist():
                    if k==5 and nr==0:forbidden.add(row['instance_id'])
                    if row['instance_id'] not in forbidden and int(base.sha(('compact-s4|'+row['instance_id']).encode()),16)%10==0:
                        ms=json.loads(row['messages'])
                        if not any(m.get('role')=='tool' for m in ms):
                            val=one(row,k,nr,ms);print(base.dump(val),file=f);included+=1
                    nr+=1
        pf.close();counts[k]=included;print(k,included,flush=True)
    (T/'source'/'cohort.json').write_text(json.dumps(counts,indent=1))
if __name__=='__main__':main()

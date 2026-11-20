"""Fetch pinned public submission assets, then project model-visible observations without reasoning."""
import argparse
import concurrent.futures
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parent
REG='40f164d5b8f1d249bf95a6df8b74b577fd8e519d'
GEM='2f6637a2557da1f7b5f2b583ab7090a077bbeed2'
GEMREPO='john-b-yang/20260901_mini-v2.4.2_gemini-3-5-flash'
S3='https://swe-bench-submissions.s3.amazonaws.com/'
SUB={'claude':'20260217_mini-v2.0.0_claude-4-6-opus','codex':'20260219_mini-v2.0.0_gpt-5-2-codex','gemini':'20260901_mini-v2.4.2_gemini-3-5-flash'}
def sha(b):return hashlib.sha256(b).hexdigest()
def js(n,x):(ROOT/n).write_text(json.dumps(x,ensure_ascii=False,indent=1)+'\n',encoding='utf8')
def get(url):
    for i in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'agent-memory-research/1.0'})
            with urllib.request.urlopen(req,timeout=60) as r:return r.read()
        except Exception:
            if i==3:raise
            time.sleep(2**i)
def list_sources():
    out=[];meta={}
    for model,sub in SUB.items():
        url=f'https://raw.githubusercontent.com/SWE-bench/experiments/{REG}/evaluation/verified/{sub}/metadata.yaml'
        content=get(url)
        (ROOT/(model+'-metadata.yaml')).write_bytes(content);meta[model]={'url':url,'sha256':sha(content)}
        if model=='gemini':
            tree=json.loads(get(f'https://api.github.com/repos/{GEMREPO}/git/trees/{GEM}?recursive=1'))
            assert not tree['truncated'] and tree['sha']==GEM
            for v in tree['tree']:
                path=v['path']
                if path.startswith('trajs/') and path.endswith('.traj.json'):
                    iid=Path(path).name.removesuffix('.traj.json')
                    out.append(dict(model=model,id=iid,url=f'https://raw.githubusercontent.com/{GEMREPO}/{GEM}/{path}',bytes=v['size'],git=v['sha']))
        else:
            prefix=f'bash-only/{sub}/trajs/'
            params={'list-type':'2','prefix':prefix}
            while True:
                z=ET.fromstring(get(S3+'?'+urlencode(params)))
                for obj in z.findall('{*}Contents'):
                    k=obj.findtext('{*}Key')
                    if k.endswith('.traj.json'):
                        iid=k.split('/')[-1].removesuffix('.traj.json')
                        out.append(dict(model=model,id=iid,url=S3+k,bytes=int(obj.findtext('{*}Size')),etag=obj.findtext('{*}ETag').strip('"')))
                if z.findtext('{*}IsTruncated')!='true':break
                params['continuation-token']=z.findtext('{*}NextContinuationToken')
    assert len({(x['model'],x['id']) for x in out})==len(out)
    js('registry.json',meta);js('list.json',out)
    return out
def project(raw):
    obj=json.loads(raw)
    cwd=obj.get('info',{}).get('config',{}).get('environment',{}).get('cwd')
    if cwd!='/testbed':raise ValueError('Unverified cwd '+str(cwd))
    rows=[];pending=None;unknown=0
    def flush():
        nonlocal pending
        if pending is not None:
            rows.append(pending)
            pending=None
    for m in obj['messages']:
        if m.get('object')=='response':
            m={'role':'assistant','tool_calls':[{'id':v['call_id'],'function':{'name':v['name'],'arguments':v['arguments']}} for v in m.get('output',[]) if v.get('type')=='function_call']}
        elif m.get('type')=='function_call_output':
            m={'role':'tool','tool_call_id':m['call_id'],'extra':m.get('extra',{}),'content':m.get('output') or ''}
        if m['role']=='assistant':
            flush()
            pending=[]
            for call in m.get('tool_calls') or []:
                fn=call.get('function') or {};args=fn.get('arguments') or '{}'
                try: args=json.loads(args) if isinstance(args,str) else args
                except (TypeError,ValueError): args={}
                pending.append({'call':call.get('id'),'command':args.get('command','') if fn.get('name')=='bash' else '', 'result':None})
        elif m['role']=='tool':
            key=m.get('tool_call_id')
            hit=[e for e in pending or [] if e['call']==key and e['result'] is None]
            if len(hit)!=1:
                unknown+=1
                if pending is None:pending=[]
                pending.append({'call':key,'command':'','result':None})
                continue
            extra=m.get('extra') or {}
            out=extra.get('raw_output');rc=extra.get('returncode')
            if isinstance(out,str) and isinstance(rc,int):
                # No future output or hidden model reasoning enters the extractor here.
                hit[0]['result']={'rc':rc,'sha':sha(out.encode()),'bytes':len(out.encode()),'visible':out in (m.get('content') or '')}
                if hit[0]['result']['visible'] and rc==0:
                    from replay import parse_read
                    if parse_read(hit[0]['command']) is not None:hit[0]['result']['text']=out
    flush()
    return {'groups':[g for g in rows if g],'orphan_tools':unknown,'verified_cwd':cwd}
def one(v):
    # Retain only exact SHA + projected command/observation records; upstream snapshots remain public.
    dest=ROOT/'events'/v['model']/(v['id']+'.json.gz')
    dest.parent.mkdir(exist_ok=True,parents=True)
    if dest.exists():
        with gzip.open(dest,'rt',encoding='utf8') as f:cached=json.load(f)
        if cached.get('verified_cwd')=='/testbed':return cached['source']
    raw=get(v['url']);assert len(raw)==v['bytes'],v
    if 'git' in v: assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==v['git']
    elif '-' not in v['etag']:assert hashlib.md5(raw).hexdigest()==v['etag']
    source={'id':v['id'],'model':v['model'],'bytes':len(raw),'sha256':sha(raw)}
    x=project(raw);x['source']=source
    data=(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    temp=dest.with_suffix('.tmp')
    temp.write_bytes(gzip.compress(data,compresslevel=4,mtime=0));temp.replace(dest)
    return source
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--list-only',action='store_true')
    args=parser.parse_args()
    listing=json.loads((ROOT/'list.json').read_text()) if (ROOT/'list.json').exists() else list_sources()
    print('public manifests',Counter(v['model'] for v in listing),sum(v['bytes'] for v in listing),flush=True)
    if args.list_only:return
    records=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=14) as executor:
        futures={executor.submit(one,v):v for v in sorted(listing,key=lambda x:sha((x['id']+x['model']).encode()))}
        for fut in concurrent.futures.as_completed(futures):
            try:r=fut.result()
            except Exception as e:
                v=futures[fut];r={'id':v['id'],'model':v['model'],'error':repr(e)}
            records.append(r)
            if len(records)%100==0:print(len(records),'complete',sum('error' in x for x in records),'errors',flush=True)
    js('sources.json',sorted(records,key=lambda x:(x['model'],x['id'])))
    if any('error' in r for r in records):raise SystemExit('Some source recoveries needed; rerun resumably.')
if __name__=='__main__':main()


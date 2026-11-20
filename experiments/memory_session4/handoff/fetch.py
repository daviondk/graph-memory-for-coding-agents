"""Fetch source-declared submission assets. No report/outcome content is read during collection of inputs."""
import concurrent.futures as cf,re,threading,time,urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
import requests
from common import *
LOCAL=threading.local()
def response(url,params=None):
    if not hasattr(LOCAL,'s'):LOCAL.s=requests.Session()
    for retry in range(5):
        try:
            r=LOCAL.s.get(url,params=params,timeout=50);r.raise_for_status();return r
        except requests.RequestException:
            if retry==4:raise
            time.sleep(1+retry)
def listing():
    lookup={}
    for m in ('claude','codex'):
        params={'list-type':2,'prefix':'bash-only/'+SUB[m]+'/logs/'}
        while True:
            root=ET.fromstring(response(S3,params).content)
            for obj in root.findall('{*}Contents'):
                path=obj.findtext('{*}Key');iid,name=path.split('/')[-2:]
                if name in ('patch.diff','report.json'):
                    lookup[f'{m}|{iid}|{name}']={'url':S3+path,'md5':obj.findtext('{*}ETag').strip('"'),'bytes':int(obj.findtext('{*}Size'))}
            token=root.findtext('{*}NextContinuationToken')
            if not token:break
            params['continuation-token']=token
    repo='john-b-yang/'+SUB['gemini']
    tree=response(f'https://api.github.com/repos/{repo}/git/trees/{GEM}',{'recursive':1}).json();assert not tree['truncated']
    for o in tree['tree']:
        path=o['path'];parts=path.split('/')
        if len(parts)>=3 and parts[0]=='logs' and parts[-1] in ('report.json','patch.diff'):
            lookup['gemini|'+parts[-2]+'|'+parts[-1]]={'url':f'https://raw.githubusercontent.com/{repo}/{GEM}/{path}','git':o['sha'],'bytes':o['size']}
    write('asset_listing.json.gz',lookup);return lookup
def validated(o):
    b=response(o['url']).content;assert len(b)==o['bytes']
    if 'md5' in o:assert hashlib.md5(b).hexdigest()==o['md5']
    if 'git' in o:assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==o['git']
    if 'sha256' in o:assert sha(b)==o['sha256']
    return b
def visible_fields(raw):
    d=json.loads(raw)
    turns=[];by_id={};group=-1
    def emit(c,key):
        turns.append({'group':group,'cmd':c,'rc':None,'diag':None,'visible_sha':None});by_id[key]=turns[-1]
    for msg in d.get('messages',[]):
        if msg.get('object')=='response':
            group+=1
            for v in msg.get('output',[]):
                if v.get('type')=='function_call':
                    args=v.get('arguments',{});args=json.loads(args) if isinstance(args,str) else args
                    emit(args.get('command','') if v['name']=='bash' else '',v['call_id'])
        elif msg.get('role')=='assistant':
            group+=1
            for v in msg.get('tool_calls') or []:
                q=v.get('function',{});args=q.get('arguments') or '{}'
                try:args=json.loads(args) if isinstance(args,str) else args
                except ValueError:args={}
                emit(args.get('command','') if q.get('name')=='bash' else '',v.get('id'))
        elif msg.get('role')=='tool' or msg.get('type')=='function_call_output':
            r=by_id.get(msg.get('tool_call_id') or msg.get('call_id'))
            if r is None:continue
            v=msg.get('content') or msg.get('output') or ''
            if not isinstance(v,str):continue
            # Only visible terminal report, never report.json or the agent's reflections.
            rc=re.search(r'<returncode>\s*(-?\d+)\s*</returncode>',v)
            if rc:r['rc']=int(rc[1])
            ex=msg.get('extra') or {}
            if rc and ex.get('returncode') is not None:assert r['rc']==ex['returncode']
            r['visible_sha']=sha(v)
            lines=[l.strip() for l in v.splitlines() if len(l)<540]
            evidence=[l for l in lines if re.search(r'(^|[ =,;])\d+ (?:passed|failed|error|errors|skipped|deselected)\b|^Ran \d+ tests? in|^OK(?: \(.*\))?$|^FAILED \((?:errors|failures)=|^(?:ModuleNotFoundError|ImportError|TimeoutExpired):',l)]
            if evidence:r['diag']=' '.join(evidence[-2:])[:230]
    inf=d.get('info') or {};sub=inf.get('submission')
    return turns,(sub if isinstance(sub,str) else '')
def collect(o,lookup):
    m,i=o['model'],o['id'];n='records/'+m+'/'+i+'.json.gz'
    if (ROOT/n).exists():return
    b=validated(o);turns,sub=visible_fields(b)
    entry=lookup.get(f'{m}|{i}|patch.diff')
    if entry:
        pb=validated(entry);patch=pb.decode('utf8',errors='replace');origin=entry['url']
    elif m=='gemini' and i in GEMP:
        patch=GEMP[i];origin='pinned all_preds.jsonl'
    else:
        patch=sub;origin='trajectory.info.submission' if sub else 'absent in evaluator listing and trajectory'
    write(n,{'model':m,'issue_id':i,'trace_url':o['url'],'trace_sha256':sha(b),'turns':turns,
             'patch':patch,'patch_origin':origin,'patch_sha256_utf8':sha(patch),'traj_submission_matches':sub==patch if sub else None})
def main():
    global GEMP
    ls=listing() if not (ROOT/'asset_listing.json.gz').exists() else read('asset_listing.json.gz')
    g=response(f'https://raw.githubusercontent.com/john-b-yang/{SUB["gemini"]}/{GEM}/all_preds.jsonl').content
    GEMP={r['instance_id']:r['model_patch'] for line in g.splitlines() if (r:=json.loads(line))}
    ids={(o['model'],o['id']):o for o in json.loads((PREV/'sources.json').read_bytes())}
    manifest=[{**o,'sha256':ids[o['model'],o['id']]['sha256']} for o in json.loads((PREV/'list.json').read_bytes())]
    write('trace_listing.json.gz',manifest);print('assets',Counter((k.split('|')[0],k.split('|')[-1]) for k in ls),'traces',len(manifest),flush=True)
    ordered=sorted(manifest,key=lambda x:sha('order|'+x['model']+x['id']))
    with cf.ThreadPoolExecutor(14) as pool:
        for i,_ in enumerate(pool.map(lambda x:collect(x,ls),ordered)):
            if i%200==199:print(i+1,flush=True)
    print('done',len(manifest))
if __name__=='__main__':main()

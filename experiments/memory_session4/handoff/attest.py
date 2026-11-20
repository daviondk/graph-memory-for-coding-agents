"""Independent source linkage audit, using only submitted patches, trajectory configuration and public hashes."""
import collections,json,re,subprocess
from concurrent.futures import ThreadPoolExecutor
from common import *
from fetch import validated,response
import xml.etree.ElementTree as ET
EXTRA=['20260128_mini-v2.0.0-toolcall_gpt-5-2','20260217_mini-v2.0.0_gpt-5-2-high']
def changed(p):
    files=[];current=None;inhunk=False
    for l in p.splitlines():
        if l.startswith('diff --git '):current=[l,[]];files.append(current);inhunk=False
        elif l.startswith('@@'):inhunk=True
        elif inhunk and current and l[:1] in ('-','+'):current[1].append(l)
    return files
def gitid(p):
    if not p:return None
    r=subprocess.run(['git','patch-id','--stable'],input=p.encode(),capture_output=True)
    return r.stdout.split()[0].decode() if r.stdout.strip() else None
def pool_assets(sub):
    ls={};params={'list-type':2,'prefix':'bash-only/'+sub+'/trajs/'}
    while True:
        z=ET.fromstring(response(S3,params).content)
        for e in z.findall('{*}Contents'):
            u=e.findtext('{*}Key')
            if u.endswith('.traj.json'):
                ls[u.split('/')[-1].removesuffix('.traj.json')]={'url':S3+u,'bytes':int(e.findtext('{*}Size')),'md5':e.findtext('{*}ETag').strip('"')}
        t=z.findtext('{*}NextContinuationToken')
        if not t:break
        params['continuation-token']=t
    return ls
def audit(o):
    m,i=o['model'],o['id'];d=json.loads(validated(o));inf=d['info'];patch=read(f'records/{m}/{i}.json.gz')['patch']
    s=inf.get('submission') or '';model=(inf.get('config',{}).get('model') or {}).get('model_name','')
    same=s==patch
    def sig(t):
        return sha(canon(changed(t)))
    return {'m':m,'id':i,'configured':model,'submitted':s,'sha_trajectory':o['sha256'],'sha_patch':sha(patch),'sha_submit':sha(s),
        'empty_submit':not s,'exact':same,'changed_lines_and_files_same':same or sig(patch)==sig(s),'gitid_eq':same or gitid(patch)==gitid(s)}
def main():
    lst=read('trace_listing.json.gz')
    others={sub:pool_assets(sub) for sub in EXTRA}
    with ThreadPoolExecutor(11) as ex:out=list(ex.map(audit,lst));write('attestation/trace_checks.json.gz',out)
    outsort={r['id']:r for r in out if r['m']=='codex'}
    samefiles={sub:sum(other.get(o['id'],{}).get('md5')==o.get('etag') for o in lst if o['model']=='codex') for sub,other in others.items()}
    write('attestation/possible_duplicates.json.gz',others)
    report={'configured':{m:dict(collections.Counter(r['configured'] for r in out if r['m']==m)) for m in MODELS},
        'conditions':{m:{k:sum(r[k] for r in out if r['m']==m) for k in ('exact','empty_submit','changed_lines_and_files_same','gitid_eq')} for m in MODELS},
        'identical_trajectory_etag_other_registered_submissions':samefiles}
    write('attestation/summary.json',report);print(report)
if __name__=='__main__':main()

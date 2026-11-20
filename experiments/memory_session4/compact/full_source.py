"""Select test files without looking at their outcomes, resolve immutable task commits and validate physical full-file edits."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
import gzip,hashlib,json,os,re,requests,subprocess,tempfile,time
from common import *
from score import intent
N=240
BASE=ROOT/'native';BASE.mkdir(exist_ok=True)
def choose():
    pairs={}
    for k in range(8):
        for row in src(k):
            for cut in range(4,len(row['events']),4):
                goal=intent(row['events'],cut)
                if not goal:continue
                path=goal[0];inst=row['instance'];repo='.'.join(inst.split('.')[:2])
                if not re.fullmatch(r'[\w.\-]+',repo) or path.startswith('/') or '..' in path.split('/'):continue
                pairs.setdefault((inst,path),{'inst':inst,'repo':repo,'path':path,'shard':k,'row':row['row'],'cut':cut})
    selected=sorted(pairs.values(),key=lambda r:hashlib.sha256(('native-s4|'+r['inst']+'|'+r['path']).encode()).hexdigest())[:N]
    (BASE/'sample.json').write_text(json.dumps(selected,indent=1));return selected
def branches(repo):
    run=subprocess.run(['git','ls-remote','--heads','https://github.com/swesmith/'+repo+'.git'],capture_output=True,timeout=100)
    if run.returncode:return repo,{}
    return repo,{ref.removeprefix('refs/heads/'):sha for line in run.stdout.decode('utf8','replace').splitlines() if '\t' in line for sha,ref in [line.split('\t',1)]}
def main():
    selected=choose()
    with ThreadPoolExecutor(8) as ex:refs=dict(ex.map(branches,sorted({r['repo'] for r in selected})))
    def get(r):
        rev=refs[r['repo']].get(r['inst']);oid=None;code=None
        if rev:
            url='https://raw.githubusercontent.com/swesmith/'+r['repo']+'/'+rev+'/'+quote(r['path'])
            for n in range(3):
                try:
                    f=requests.get(url,timeout=(15,25));code=f.status_code
                    if f.ok:
                        data=f.content
                        oid=hashlib.sha256(data).hexdigest();dest=BASE/'blobs'/(oid+'.gz')
                        if not dest.is_file():
                            with gzip.open(dest,'wb') as fh:fh.write(data)
                        break
                    if code<500 and code!=429:break
                except requests.RequestException:code=-1
        return {**r,'commit':rev,'status':code,'blob_sha256':oid}
    (BASE/'blobs').mkdir(exist_ok=True)
    with ThreadPoolExecutor(12) as ex:rs=list(ex.map(get,selected))
    (BASE/'sources.json').write_text(json.dumps(rs,indent=1))
    print(len(selected),dict(Counter(v['status'] for v in rs)),flush=True)
if __name__=='__main__':main()

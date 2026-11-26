"""Verify signed R40 research files, portable demos, format inventory and optional Git blobs."""
import argparse
from collections import Counter
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
from urllib.parse import unquote,urlsplit
import zipfile

ROOT=Path(__file__).resolve().parent
BASE_TOP=('REPORT_RU.md','release.json','FILE_TYPES.json','verify.py','package_verified.py','import_verified.py')
OUTER='MANIFEST_SHA256.json'

def require(ok,message):
    if not ok:raise ValueError(message)

def digest(data):return hashlib.sha256(data).hexdigest()
def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def valid_name(name):
    p=PurePosixPath(name)
    return bool(p.parts) and not p.is_absolute() and p.as_posix()==name and not any(x in {'.','..','.git'} for x in p.parts) and ':' not in name and '\\' not in name and '\x00' not in name

def entries(manifest):
    return {n:value if isinstance(value,str) else value['sha256'] for n,value in manifest.get('files',manifest).items()}

def classify(name,data):
    suffix=PurePosixPath(name).suffix.lower()
    if name.endswith('.json.gz'):
        require(data[:2]==b'\x1f\x8b',name);json.loads(gzip.decompress(data));return 'gzip-compressed JSON'
    if suffix=='.json':json.loads(data);return 'JSON'
    if suffix=='.dll':
        require(data[:2]==b'MZ' and len(data)>64,name)
        ofs=struct.unpack_from('<I',data,60)[0]
        require(data[ofs:ofs+4]==b'PE\0\0' and struct.unpack_from('<H',data,ofs+22)[0]&0x2000,name)
        return 'Windows PE dynamic library'
    if suffix=='.sqlite':require(data.startswith(b'SQLite format 3\0'),name);return 'SQLite 3 database'
    if suffix=='.pdf':require(data.startswith(b'%PDF-'),name);return 'PDF'
    if suffix=='.mp4':require(data[4:8]==b'ftyp',name);return 'ISO BMFF / MP4 video'
    if suffix=='.png':require(data.startswith(b'\x89PNG\r\n\x1a\n'),name);return 'PNG image'
    if suffix=='.zip':require(zipfile.is_zipfile(BytesIO(data)),name);return 'ZIP archive'
    kinds={'.md':'Markdown','.py':'Python source','.cpp':'C++ source','.tex':'LaTeX source','.bib':'BibTeX','.html':'HTML','.csv':'CSV','.ps1':'PowerShell source','.jsonl':'JSON Lines','.txt':'UTF-8 text'}
    require(suffix in kinds,f'Unregistered file format: {name}');data.decode('utf-8');return kinds[suffix]

def extra_demo_files(release,load):
    runtime=release['demo_runtime']
    seal=json.loads(load('demo_revision/runtime-inputs.json'))
    require(seal['origin_manifest']==runtime['origin_manifest'],'runtime provenance digest')
    result={'demo_revision/runtime/'+f:h for f,h in seal['files'].items()}
    for name,info in release['demo_archives'].items():
        require(valid_name(name) and name.endswith('.zip'),name)
        owner=info['study'];require(owner in release['completed'] and name.startswith(owner+'/'),name)
        raw=load(name);require(digest(raw)==info['sha256'],name)
        with zipfile.ZipFile(BytesIO(raw)) as z:
            inner=entries(json.loads(z.read('manifest.json')))
            expected=dict(inner);expected['manifest.json']=release['manifests'][owner]
            if owner=='demo_revision':expected.update({'runtime/'+f:h for f,h in seal['files'].items()})
            require(len(z.namelist())==len(expected) and set(z.namelist())==set(expected),name)
            for member,h in expected.items():require(valid_name(member) and digest(z.read(member))==h,f'{name}/{member}')
        result[name]=info['sha256']
    return result

def expected(release,load):
    studies=release['completed'];top=list(BASE_TOP)+release['top_documents']
    require(release['round']==40 and studies==sorted(set(studies)) and set(studies)==set(release['manifests']), 'study register')
    require(all(valid_name(x) for x in top+studies) and all('/' not in x for x in studies),'invalid register path')
    files={name:digest(load(name)) for name in top}
    for study in studies:
        key=study+'/manifest.json';raw=load(key);require(digest(raw)==release['manifests'][study],key);files[key]=digest(raw)
        child=entries(json.loads(raw));require('REPORT_RU.md' in child,study)
        for name,sha in child.items():
            require(valid_name(name) and name!='manifest.json' and re.fullmatch('[0-9a-f]{64}',sha),name)
            files[study+'/'+name]=sha
    extra=extra_demo_files(release,load)
    require(not set(files)&set(extra),'duplicate separately registered payload')
    files.update(extra)
    for name,sha in files.items():require(digest(load(name))==sha,name)
    return dict(sorted(files.items()))

def crosslinks(root,names):
    prior=set()
    for name in names:
        if not name.endswith('.md'):continue
        doc=root/name
        for address in re.findall(r'\]\(([^()\s]+)\)',doc.read_text(encoding='utf8')):
            url=urlsplit(address)
            if url.scheme in ('https','http','mailto') or not url.path:continue
            dest=(doc.parent/unquote(url.path)).resolve()
            if dest.is_relative_to(root):
                require(dest.relative_to(root).as_posix() in names,f'unbundled target {name} -> {address}')
            else:
                require(dest.is_relative_to(root.parent),f'local target outside prior rounds {address}')
                key=dest.relative_to(root.parent).as_posix();require(re.fullmatch(r'graph_memory_round(?:[1-9]|[123][0-9])/.+',key),key);prior.add(key)
    return sorted(prior)

def verify(root=ROOT):
    root=root.resolve();release=read(root/'release.json')
    def load(name):
        require(valid_name(name) and (root/name).resolve().is_relative_to(root),name);return (root/name).read_bytes()
    files=expected(release,load);types=read(root/'FILE_TYPES.json');payload=set(files)-{'FILE_TYPES.json','release.json'}
    require(set(types['files'])==payload,'typed inventory membership')
    for name,info in types['files'].items():
        require(info=={'type':classify(name,load(name)),'bytes':len(load(name))},name)
    require(types['counts']==dict(Counter(x['type'] for x in types['files'].values())),'format totals')
    require(crosslinks(root,files)==release['prior_series_links'],'external relative link register')
    for test in release['outcome_checks']:
        obj=read(root/test['file'])
        for key in test['path']:obj=obj[key]
        require(obj==test['equals'],test)
    if (root/OUTER).is_file():require(read(root/OUTER)==files,'outer manifest')
    return files

def verify_git(root,ref,files):
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args])
    repo=Path(git('rev-parse','--show-toplevel').decode().strip()).resolve()
    prefix=root.resolve().relative_to(repo).as_posix();tracked=set(git('ls-tree','-r','--name-only','-z',ref,'--','.').decode().strip('\0').split('\0'))
    names=set(files)|{OUTER};require(tracked==names,f'Git inventory difference: {tracked^names}')
    for n in names:require(digest(git('cat-file','blob',f'{ref}:{prefix}/{n}'))==digest((root/n).read_bytes()),n)
    for prior in read(root/'release.json')['prior_series_links']:git('cat-file','-e',f'{ref}:{PurePosixPath(prefix).parent/prior}')
    return len(names)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--git-ref');args=p.parse_args()
    files=verify();print('Verified',len(read(ROOT/'release.json')['completed']),'studies and',len(files),'files')
    if args.git_ref:print('Verified Git blobs:',verify_git(ROOT,args.git_ref,files))

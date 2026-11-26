"""Verify signed R43 research files, portable demos, format inventory and optional Git blobs."""
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
    if suffix=='.npz':
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names=archive.namelist()
            require(bool(names) and len(names)==len(set(names)),name)
            for item in names:
                require(valid_name(item) and item.endswith('.npy'),name)
                with archive.open(item) as vector:
                    require(vector.read(6)==b'\x93NUMPY',name)
        return 'NumPy array archive'
    if suffix=='.zip':require(zipfile.is_zipfile(BytesIO(data)),name);return 'ZIP archive'
    kinds={'.md':'Markdown','.py':'Python source','.cpp':'C++ source','.tex':'LaTeX source','.bib':'BibTeX','.html':'HTML','.csv':'CSV','.ps1':'PowerShell source','.jsonl':'JSON Lines','.txt':'UTF-8 text','.log':'Text log','.err':'Stderr log'}
    require(suffix in kinds,f'Unregistered file format: {name}');data.decode('utf-8');return kinds[suffix]

def expected(release,load):
    studies=release['completed'];top=list(BASE_TOP)+release['top_documents']
    require(release['round']==43 and studies==sorted(set(studies)) and set(studies)==set(release['manifests']), 'study register')
    require(all(valid_name(x) for x in top+studies) and all('/' not in x for x in studies),'invalid register path')
    files={name:digest(load(name)) for name in top}
    for study in studies:
        key=study+'/manifest.json';raw=load(key);require(digest(raw)==release['manifests'][study],key);files[key]=digest(raw)
        child=entries(json.loads(raw));require('REPORT_RU.md' in child,study)
        for name,sha in child.items():
            require(valid_name(name) and name!='manifest.json' and re.fullmatch('[0-9a-f]{64}',sha),name)
            files[study+'/'+name]=sha
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
                key=dest.relative_to(root.parent).as_posix();require(re.fullmatch(r'graph_memory_round(?:[1-9]|[123][0-9]|4[012])/.+',key) or key=='memory_session5/packets/common.py',key);prior.add(key)
    return sorted(prior)

def verify_retraining(root):
    study=root/'checkpoint_selection'
    changed=[0,0]
    equal_winners=0
    for seed in (13,17,29,37,41):
        pairs=read(study/f'paired-{seed}.json.gz')
        for idx,arm in enumerate(('full_rgcn','wo_chunk_adjacency')):
            with zipfile.ZipFile(study/f'dev-{seed}-{arm}.zip') as z:
                record=json.loads(z.read('ledger.json'))
                for name,k in [('native-checkpoint.json','original_epoch'),('replay-checkpoint.json','repeated_epoch')]:
                    history=json.loads(z.read(name))['records']
                    initial=history[0]['initial_dev_recall_at_5']
                    all_epochs=[initial]+[row['dev_recall_at_5'] for row in history]
                    require(all_epochs.index(max(all_epochs))==record[k],f'{seed}/{arm}/{name}')
            if record['repeated_epoch']==record['selected']['epoch']:
                equal_winners+=1
                for row in pairs.values():
                    old,new=row[3+idx][0],row[5+idx][0]
                    changed[0]+=new>old
                    changed[1]+=new<old
    require(equal_winners==5 and changed==[264,263],'retraining contrast with equal criteria winners')

def verify(root=ROOT):
    root=root.resolve();release=read(root/'release.json')
    def load(name):
        require(valid_name(name) and (root/name).resolve().is_relative_to(root),name);return (root/name).read_bytes()
    if 'checkpoint_selection' in release['completed']:verify_retraining(root)
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
    prefix=root.resolve().relative_to(repo).as_posix()
    rows=git('ls-tree','-r','-z',ref,'--','.')
    tracked={}
    for raw in rows.split(b'\0'):
        if not raw:
            continue
        meta,name=raw.split(b'\t',1)
        mode,kind,oid=meta.split()
        require(kind==b'blob' and mode in (b'100644',b'100755'),name)
        tracked[name.decode('utf8')]=oid
    names=sorted(set(files)|{OUTER})
    require(set(tracked)==set(names),'Git tree membership differs from release')
    ids=[tracked[name] for name in names]
    # cat-file returns length-prefixed bytes for each requested object in order.
    blob_stream=BytesIO(subprocess.check_output(
        ['git','-C',str(root),'cat-file','--batch'],input=b'\n'.join(ids)+b'\n'))
    for name,oid in zip(names,ids):
        header=blob_stream.readline().split()
        require(len(header)==3 and header[:2]==[oid,b'blob'],name)
        blob=blob_stream.read(int(header[2]))
        require(blob_stream.read(1)==b'\n',name)
        require(digest(blob)==digest((root/name).read_bytes()),name)
    require(blob_stream.read()==b'','unexpected Git output')
    for prior in read(root/'release.json')['prior_series_links']:git('cat-file','-e',f'{ref}:{PurePosixPath(prefix).parent/prior}')
    return len(names)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--git-ref');args=p.parse_args()
    files=verify();print('Verified',len(read(ROOT/'release.json')['completed']),'studies and',len(files),'files')
    if args.git_ref:print('Verified Git blobs:',verify_git(ROOT,args.git_ref,files))

import os,hashlib,json,sys,time,urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import requests
base=Path(os.environ.get('SWE_CONTEXT_DATA','D:/CodexResearch/x20-swe-context'));base.mkdir(exist_ok=True,parents=True)
here=Path(__file__).resolve().parent
repo='jiayuanz3/SWEContextBench';rev='12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b';hf='12c65bd15e2559bc808065565e941ee7bbbd008f'
def dl(url):
    for i in range(5):
        try:r=requests.get(url,timeout=90);r.raise_for_status();return r.content
        except requests.RequestException:
            if i==4:raise
            time.sleep(1+i)
tree=json.loads(dl(f'https://api.github.com/repos/{repo}/git/trees/{rev}?recursive=1'))['tree']
items=[r for r in tree if r['type']=='blob' and (r['path'].startswith('cases/SWEContextBench Lite Past Experience/') or r['path'].startswith('cases/SWEContextBench Lite/'))]
def fetch(r):
    rel=r['path'];parent='traces' if rel.endswith('.jsonl') else 'case_metadata';path=base/parent/Path(rel).name;path.parent.mkdir(exist_ok=True)
    x=path.read_bytes() if path.is_file() else dl(f'https://raw.githubusercontent.com/{repo}/{rev}/'+urllib.parse.quote(rel))
    assert hashlib.sha1(b'blob '+str(len(x)).encode()+b'\0'+x).hexdigest()==r['sha']
    if not path.exists():path.write_bytes(x)
    return {'relative':parent+'/'+path.name,'git_blob':r['sha'],'size':len(x),'sha256':hashlib.sha256(x).hexdigest()}
with ThreadPoolExecutor(max_workers=7) as e:rows=list(e.map(fetch,items))
for name in ('SWEContextBench_Related_Lite.parquet','SWEContextBench_Relationship.parquet','SWEContextBench_Related.parquet'):
    p=base/name;x=dl('https://huggingface.co/datasets/'+repo+'/resolve/'+hf+'/data/'+name);p.write_bytes(x);rows.append({'relative':name,'size':len(x),'sha256':hashlib.sha256(x).hexdigest()})
(here/'source.json').write_text(json.dumps({'github':rev,'hf':hf,'files':rows},indent=2),encoding='utf8')
print('assets',len(rows),'bytes',sum(r['size'] for r in rows))


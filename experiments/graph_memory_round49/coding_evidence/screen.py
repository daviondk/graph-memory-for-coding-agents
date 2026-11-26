"""Select tasks from public columns and container manifests only; no outcome labels."""
from pathlib import Path
import concurrent.futures,hashlib,json,subprocess,urllib.parse,shutil
import pyarrow.parquet as pq
D=Path(__file__).resolve().parent
DATA=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench/benchmark/test.parquet")
REPOS={"alteryx/woodwork","HypothesisWorks/hypothesis","sdv-dev/RDT"}
def download(url,headers=()):
    cmd=['curl.exe','-fsS','--retry','2','--max-time','30']
    for h in headers:cmd+=['-H',h]
    return subprocess.check_output([*cmd,url],stderr=subprocess.PIPE)
def query(r):
    img=r['image_name'].removeprefix('docker.io/');repo,tag=img.split(':')
    tok=json.loads(download('https://auth.docker.io/token?'+urllib.parse.urlencode(dict(service='registry.docker.io',scope='repository:'+repo+':pull'))))['token']
    headers=['Authorization: Bearer '+tok,'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json']
    prefix='https://registry-1.docker.io/v2/'+repo+'/manifests/'
    raw=download(prefix+tag,headers);m=json.loads(raw)
    if 'manifests' in m:
        md=next(x['digest'] for x in m['manifests'] if x.get('platform',{}).get('os')=='linux' and x['platform']['architecture']=='amd64')
        raw=download(prefix+md,headers);m=json.loads(raw);assert 'sha256:'+hashlib.sha256(raw).hexdigest()==md
    return {**r,'image':repo+'@sha256:'+hashlib.sha256(raw).hexdigest(),'layers':{x['digest']:x['size'] for x in m['layers']}}
rows=pq.read_table(DATA,columns=['repo','instance_id','base_commit','image_name','problem_statement','created_at']).to_pylist()
assert len(rows)==111
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:data=list(pool.map(query,[r for r in rows if r['repo'] in REPOS]))
groups={}
for repo in REPOS:
    union={}
    for r in data:
        if r['repo']==repo:union.update(r['layers'])
    groups[repo]=sum(union.values())
obj={'data_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),'selection_sha256':hashlib.sha256((D/'SELECTION_RU.md').read_bytes()).hexdigest(),'rows':data,'total_rows':len(rows),'bytes_by_repo':groups,'free_bytes_at_screen':shutil.disk_usage(D).free}
(D/'screen.json').write_text(json.dumps(obj,default=str,sort_keys=True,ensure_ascii=False,indent=2),encoding='utf8')
for repo,b in sorted(groups.items(),key=lambda v:v[1]):
    print(repo,b)
    for r in data:
        if r['repo']==repo:print(r['instance_id'],r['problem_statement'][:400])

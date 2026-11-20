import concurrent.futures,datetime,hashlib,json
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from pathlib import Path
ROOT=Path(__file__).resolve().parent
URLS=[
'https://huggingface.co/api/datasets/jiayuanz3/SWEContextBench',
'https://api.github.com/repos/jiayuanz3/SWEContextBench/git/trees/main?recursive=1',
'https://api.github.com/repos/C-lister/SWE-Edit/git/trees/main?recursive=1',
'https://api.github.com/repos/THU-Agent/continual-harness-evolution/git/trees/main?recursive=1',
'https://api.github.com/repos/thomasjoshi/agents-never-forget/git/trees/main?recursive=1',
'https://api.github.com/repos/Farhana211/Hierarchical-Caching-for-Agentic-Workflows/git/trees/main?recursive=1',
'https://api.github.com/repos/t46/compactionbench/git/trees/main?recursive=1',
'https://api.github.com/repos/ayushnangia/CompactionBench/git/trees/main?recursive=1']
def get(u):
    try:
        with urlopen(Request(u,headers={'User-Agent':'paper-availability-audit'}),timeout=45) as f:raw=f.read();status=f.status
    except HTTPError as e:return {'url':u,'http':e.code}
    j=json.loads(raw);r={'url':u,'http':status,'sha256':hashlib.sha256(raw).hexdigest(),'revision':j.get('sha'),'truncated':j.get('truncated')}
    if 'tree' in j:r['files']=[x['path'] for x in j['tree'] if x['type']=='blob']
    else:r['files']=[x['rfilename'] for x in j.get('siblings',[])];r['description']=j.get('description')
    return r
with concurrent.futures.ThreadPoolExecutor(6) as pool:results=list(pool.map(get,URLS))
(ROOT/'access_receipts_extra.json').write_text(json.dumps({'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records':results},indent=1))
for r in results:print(json.dumps({k:v for k,v in r.items() if k!='description'}))


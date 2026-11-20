"""Pin evidence for artifact availability. No code repositories are executed."""
import concurrent.futures,datetime,hashlib,json,re
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parent
URLS=[
'https://arxiv.org/html/2610.27377v1',
'https://arxiv.org/html/2611.17316v1',
'https://arxiv.org/html/2611.03219v1',
'https://arxiv.org/html/2609.32391v1',
'https://www.microsoft.com/en-us/research/publication/benchmarking-long-horizon-agent-context-compaction-with-compactionbench/',
'https://api.github.com/search/repositories?q=CompactionBench',
'https://api.github.com/search/repositories?q=Continual-SWE',
'https://huggingface.co/api/datasets?search=CompactionBench&limit=50',
'https://huggingface.co/api/datasets?search=Continual-SWE&limit=50',
'https://huggingface.co/api/datasets/C-lister/ChainSWE',
'https://api.github.com/repos/C-lister/SWE-Edit',
'https://api.github.com/repos/THU-Agent/continual-harness-evolution']
def get(url):
    try:
        with urlopen(Request(url,headers={'User-Agent':'academic-artifact-availability-audit'}),timeout=60) as fp:raw=fp.read();status=fp.status
    except HTTPError as ex:return {'url':url,'http':ex.code}
    out={'url':url,'http':status,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    if 'api.github.com' in url or 'huggingface.co/api/' in url:
        data=json.loads(raw)
        if isinstance(data,list):out['results']=[d.get('id') for d in data]
        elif 'items' in data:out['total_count']=data.get('total_count');out['results']=[{k:x.get(k) for k in ('full_name','html_url','description','pushed_at')} for x in data['items']]
        else:
            out['metadata']={k:data.get(k) for k in ('id','full_name','sha','default_branch','updated_at','lastModified','private','gated','html_url','description')}
            if 'siblings' in data:out['files']=[s['rfilename'] for s in data['siblings']]
    else:
        html=raw.decode(errors='replace')
        out['artifact_links']=sorted(set(re.findall(r'href=["\']([^"\']*(?:github.com|huggingface.co|zenodo.org)[^"\']*)',html)))
    return out
with concurrent.futures.ThreadPoolExecutor(6) as pool:out=list(pool.map(get,URLS))
(ROOT/'access_receipts.json').write_text(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'records':out},indent=1))
for r in out:print(json.dumps(r))


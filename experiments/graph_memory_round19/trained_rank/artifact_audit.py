"""Inventory the article source bundle, author-linked repositories and formal release endpoints."""
from prepare import ROOT,RUN,put,pilot
import hashlib,io,json,subprocess,tarfile
import requests
def run():
    gh='https://api.github.com/repos/xiaoqi-7/GraphMemory/'
    endpoints={
      'github_releases':gh+'releases?per_page=100','github_branches':gh+'branches?per_page=100','github_tags':gh+'tags?per_page=100',
      'github_tree':gh+'git/trees/'+pilot.CODE+'?recursive=1','hf_model_search':'https://huggingface.co/api/models?search=ISETrace&limit=100',
      'hf_model_author':'https://huggingface.co/api/models?author=HazeLocus&limit=100',
      'hf_query_data':'https://huggingface.co/api/datasets/HazeLocus/ISETrace-Memory-Queries/tree/3130aeeaeb2b8d292c29f4c8e23303be7463732c?recursive=true&limit=100',
      'hf_raw_data':'https://huggingface.co/api/datasets/valiere/ISETrace/tree/e40e04d41c04e4eb4bae181ebdd41b61c688081b?recursive=true&limit=100',
      'hf_data_search':'https://huggingface.co/api/datasets?search=ISETrace&limit=100'}
    endpoints.update({'hf_model_graphmemory':'https://huggingface.co/api/models?search=GraphMemory&limit=100',
       'hf_model_epgm':'https://huggingface.co/api/models?search=EPGM&limit=100',
       'hf_model_github_author':'https://huggingface.co/api/models?author=xiaoqi-7&limit=100',
       'hf_model_raw_author':'https://huggingface.co/api/models?author=valiere&limit=100'})
    records={};filetypes=('.pt','.pth','.ckpt','.safetensors','.npy','.npz','.jsonl','.parquet','.bin','.onnx','.pkl','.zip','.tar','.gz')
    for n,url in endpoints.items():
        try:
            r=requests.get(url,timeout=15);d=r.json()
            item=dict(url=url,status=r.status_code,sha256=hashlib.sha256(r.content).hexdigest(),pagination=r.headers.get('Link'))
            if n=='github_tree' and r.ok:
                ls=d['tree'];item.update(total=len(ls),truncated=d['truncated'],candidates=[(x['path'],x.get('size')) for x in ls if x['path'].endswith(filetypes) or 'result' in x['path'].lower() or 'ranked' in x['path'].lower()])
            elif r.ok and isinstance(d,list):item.update(n=len(d),entries=[x.get('path') or x.get('id') or x.get('name') or x.get('tag_name') for x in d])
            else:item['error']=str(d)[:160]
        except Exception as e:item=dict(url=url,error=str(e))
        records[n]=item
    for base in ['https://arxiv.org/src/2609.25913v3','https://export.arxiv.org/e-print/2609.25913v3','https://arxiv.org/e-print/2609.25913v3']:
        try:
            with requests.get(base,timeout=(8,18),stream=True) as r:
                b=b''
                for chunk in r.iter_content(262144):
                    b+=chunk
                    if len(b)>48*1024**2:raise ValueError('paper source exceeds 48 MiB')
                entry=dict(url=base,status=r.status_code,size=len(b),sha256=hashlib.sha256(b).hexdigest(),content_type=r.headers.get('content-type'))
                if r.ok:
                    with tarfile.open(fileobj=io.BytesIO(b),mode='r:*') as t:
                        entry['files']=[dict(name=f.name,size=f.size) for f in t if f.isfile()]
                    (RUN/'article-source.tar').write_bytes(b)
                    records['arxiv_source']=entry;break
                records[base]=entry
        except Exception as e:records[base]=dict(url=base,error=str(e))
    put(ROOT/'public-artifact-audit.json',records)
    print({n:(r.get('status'),r.get('n'),len(r.get('files',[]))) for n,r in records.items()})
if __name__=='__main__':run()

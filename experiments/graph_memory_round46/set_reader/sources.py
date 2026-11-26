"""Read-only audit of public reference release; no predictions or data are sent."""
from core import *
import requests
def main():
    sess=requests.Session()
    def get(url):
        r=sess.get(url,timeout=30);r.raise_for_status();return r
    repo='https://api.github.com/repos/LordTARN1SHED/SERBench';commit=get(repo+'/commits/main').json()['sha']
    tree=get(repo+'/git/trees/'+commit+'?recursive=1').json();assert not tree['truncated']
    paths=[p['path'] for p in tree['tree']]
    raw='https://raw.githubusercontent.com/LordTARN1SHED/SERBench/'+commit+'/'
    refs={}
    for f in paths:
        if not f.startswith('reference_results/') or not f.endswith('.json') or f.endswith('manifest.json'):continue
        z=get(raw+f);o=z.json();refs[f]=dict(sha=hashlib.sha256(z.content).hexdigest(),fields=sorted(o),content=o)
    docs=get(raw+'docs/REPRODUCTION.md')
    hf=get('https://huggingface.co/api/models/Qwen/Qwen3-Reranker-8B?blobs=true').json()
    b=sum(f.get('size',0) for f in hf['siblings'] if f['rfilename'].endswith('.safetensors'))
    prior=W/'graph_memory_round37/serbench_reference';assert sha(prior/'availability.json')==read(prior/'manifest.json')['availability.json'];legacy=read(prior/'availability.json')
    write('public-audit.json',dict(commit=commit,tree=paths,reference=refs,reproduction=hashlib.sha256(docs.content).hexdigest(),weight_8b_bytes=b,
        weight_8b_revision=hf['sha'],prior_sha=sha(W/'graph_memory_round37/serbench_reference/availability.json'),prior_same_tree=legacy['revision']==commit,
        local_GGUF_before=['Qwen3-4B-Instruct-2507-Q4_K_M','Qwen3.8-27B-UD-Q4_K_M','Qwen3-Embedding-8B-Q4_K_M'],
        free_before_bytes=7899877376,arxiv='https://arxiv.org/html/2609.20050v3',optional_model='https://huggingface.co/gorse-io/Qwen3-Reranker-0.6B-GGUF/tree/7af0c7c371b5ad3daf771ce4f6d091a4d38c799a'))
    print('Captured',len(paths),'public paths and',len(refs),'published method outputs; 8B BF16 bytes:',b)
if __name__=='__main__':main()

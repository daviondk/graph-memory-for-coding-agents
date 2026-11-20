"""Download pinned public sources to the experiment directory and separate histories from labels."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import urllib.request
ROOT=Path(__file__).resolve().parent
HF='https://huggingface.co/datasets/caijanfeng/compact-bench/resolve/ff20521e6a2293ba74317efb076f0c338ca5fb6b/'
GH='https://raw.githubusercontent.com/cai-jianfeng/compact-bench/9dd9a3f5a91b2de5acdf56cee2fc0a4d16dcefc5/'
SOURCES={'cb_common.py':GH+'harness/cb_common.py','e2_score.py':GH+'harness/e2_score.py','github_LICENSE.txt':GH+'LICENSE','data_NOTICE.md':HF+'NOTICE.md','data_LICENSE.txt':HF+'LICENSE','data_README.md':HF+'README.md','SHA256SUMS.txt':HF+'SHA256SUMS','sessions.jsonl':HF+'e2/sessions.jsonl','cb_data.py':GH+'harness/cb_data.py'}
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch(kv):
    k,u=kv
    folder=ROOT/'source'
    folder.mkdir(exist_ok=True)
    path=folder/k
    if not path.exists():
        with urllib.request.urlopen(u,timeout=180) as resp:
            data=resp.read()
        path.write_bytes(data)
    b=path.read_bytes()
    return k,{'url':u,'size':len(b),'sha256':sha(b)}
def main():
    with ThreadPoolExecutor(5) as pool: info=dict(pool.map(fetch,SOURCES.items()))
    assert info['sessions.jsonl']['sha256']=='5137e63af45513c1b8b7d40960735a8e545e887299ea422562443f58a97d4c09'
    (ROOT/'source_manifest.json').write_text(json.dumps(info,indent=2),encoding='utf8')
    with (ROOT/'source/sessions.jsonl').open(encoding='utf8') as f,gzip.open(ROOT/'histories.jsonl.gz','wt',encoding='utf8',compresslevel=5) as h,gzip.open(ROOT/'gold.jsonl.gz','wt',encoding='utf8',compresslevel=5) as g:
        for i,line in enumerate(f):
            r=json.loads(line)
            h.write(json.dumps({'i':i,'H':r['H']},ensure_ascii=False)+'\n')
            g.write(json.dumps({k:r[k] for k in ('sample_id','sess','client','n_atoms','atoms','future_req_ids')},ensure_ascii=False)+'\n')
if __name__=='__main__':main()


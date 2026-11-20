import hashlib, json, os, sys
from pathlib import Path
import requests
base=Path(sys.argv[1])
base.mkdir(parents=True, exist_ok=True)
repo='cross-encoder/ms-marco-MiniLM-L-6-v2'
rev='233902d25c440f23af6f7d6e94d2946bac0bee0a'
api=requests.get(f'https://huggingface.co/api/models/{repo}/tree/{rev}',timeout=40)
api.raise_for_status()
entries={x['path']:x for x in api.json()}
files={}
for name in ['config.json','tokenizer_config.json','tokenizer.json','vocab.txt','special_tokens_map.json','model.safetensors']:
    p=base/name
    if not p.exists():
        with requests.get(f'https://huggingface.co/{repo}/resolve/{rev}/{name}',stream=True,timeout=90) as r:
            r.raise_for_status()
            with p.with_suffix('.partial').open('wb') as f:
                for b in r.iter_content(1048576): f.write(b)
        p.with_suffix('.partial').replace(p)
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    ref=entries[name]
    assert p.stat().st_size==ref['size']
    if ref.get('lfs'): assert digest==ref['lfs']['oid']
    files[name]=digest
print(json.dumps({'repo':repo,'revision':rev,'files':files},indent=2))


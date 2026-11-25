"""Download the pinned seven-file Hugging Face snapshot into the model directory on D."""
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import quote
import hashlib
import json
import shutil
import sys
from time import sleep
MODEL=Path('D:/CodexResearch/x20-published-reader/model')
REV='6a967332efedfe5aca9b85b8310cc68d9ac6f881'
NAMES=['README.md','config.json','modeling_verbatim_rag.py','special_tokens_map.json','tokenizer.json','tokenizer_config.json','model.safetensors']
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def fetch():
    plan=json.loads((Path(__file__).parent/'plan.json').read_bytes())['sha_model']
    MODEL.mkdir(parents=True,exist_ok=True)
    for n in NAMES:
        dest=MODEL/n
        if dest.exists():
            if digest(dest)!=plan[n]:raise ValueError(f'Existing file differs from pinned {n}')
            continue
        part=MODEL/(n+'.partial')
        for attempt in range(3):
            try:
                with urlopen(f'https://huggingface.co/KRLabsOrg/verbatim-rag-modern-bert-v2/resolve/{REV}/{quote(n)}',timeout=90) as req,part.open('wb') as out:
                    shutil.copyfileobj(req,out,1024*1024)
                assert digest(part)==plan[n]
                part.replace(dest);break
            except (OSError,AssertionError):
                if attempt==2:raise
                sleep(1)
    print('Verified',len(NAMES),'published model files.')
if __name__=='__main__':fetch()

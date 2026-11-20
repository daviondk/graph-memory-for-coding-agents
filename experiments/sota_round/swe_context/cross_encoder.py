"""Evaluate the named 12-layer secondary control; keep initial six-layer result too."""
import hashlib
import json
import os
import time
from pathlib import Path
import numpy as np
import requests
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from rank import ROOT, dump

MODEL='cross-encoder/ms-marco-MiniLM-L-12-v2'
PATH=Path(os.environ.get('SWE_CONTEXT_L12','D:/CodexResearch/x20-swe-context/minilm12'))


def pin():
    PATH.mkdir(exist_ok=True,parents=True)
    manifest=ROOT/'cross_encoder_pin.json'
    rev=json.loads(manifest.read_text())['commit'] if manifest.exists() else requests.get('https://huggingface.co/api/models/'+MODEL,timeout=40).json()['sha']
    r=requests.get(f'https://huggingface.co/api/models/{MODEL}/tree/{rev}',timeout=40);r.raise_for_status()
    tree={v['path']:v for v in r.json()}
    files={}
    for name in ('model.safetensors','config.json','tokenizer_config.json','vocab.txt','special_tokens_map.json','tokenizer.json'):
        if name not in tree:continue
        to=PATH/name
        if not to.is_file():
            with requests.get(f'https://huggingface.co/{MODEL}/resolve/{rev}/{name}',stream=True,timeout=80) as response:
                response.raise_for_status()
                with to.with_suffix('.part').open('wb') as f:
                    for chunk in response.iter_content(2**20):
                        f.write(chunk)
            to.with_suffix('.part').replace(to)
        with to.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
        assert to.stat().st_size==tree[name]['size']
        if tree[name].get('lfs'):assert sha==tree[name]['lfs']['oid']
        files[name]=sha
    dump('cross_encoder_pin.json',{'repo':MODEL,'commit':rev,'files':files})


def main():
    start=time.time()
    ranksfile=ROOT/'blind_ranks.json'
    rows=json.loads(ranksfile.read_text(encoding='utf8'))
    queries=json.loads((ROOT/'queries.json').read_text(encoding='utf8'))
    cards=json.loads((ROOT/'cards.json').read_text(encoding='utf8'))
    flat={c['key']:' '.join(c[f] for f in ('symptom','edits','closure')) for c in cards}
    model=AutoModelForSequenceClassification.from_pretrained(PATH,local_files_only=True).eval()
    assert model.config.num_hidden_layers==12
    tok=AutoTokenizer.from_pretrained(PATH,local_files_only=True)
    with torch.inference_mode():
        for row,q in zip(rows,queries):
            if 'minilm6' not in row:row['minilm6']=row['minilm']
            top=row['fusion'][:5]
            x=tok([q['query']]*5,[flat[k] for k in top],truncation=True,max_length=512,padding=True,return_tensors='pt')
            vals=model(**x).logits[:,0].numpy()
            row['minilm']=[top[j] for j in np.argsort(-vals,kind='stable')]+row['fusion'][5:]
    sha=dump('blind_ranks.json',rows)
    input_digests={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['cards.json','queries.json','rank_run.json']}
    dump('cross_encoder_run.json',{'elapsed_seconds':time.time()-start,'final_blind_ranks_sha256':sha,'input_sha256':input_digests,'secondary':'minilm','other_control':'minilm6'})


if __name__=='__main__':
    import sys
    pin()
    if '--download-only' not in sys.argv:main()


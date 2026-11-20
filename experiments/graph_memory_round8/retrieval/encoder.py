"""Re-create the pinned official encoder locally with CPU attention."""
import hashlib
import json
import os
from pathlib import Path
import sys

from acquire import CACHE, ROOT
BACKEND='92d97331f1f4b6a366c1f161354b9f3390cc219f'
PREFIX='Represent this query for searching relevant code: '
def install_backend():
    import requests
    folder=CACHE/'snowflake_cpu'
    folder.mkdir(exist_ok=True)
    (folder/'__init__.py').touch()
    files={}
    for name in ['configuration_hf_nomic_bert.py','modeling_hf_nomic_bert.py']:
        path=folder/name
        if not path.exists():
            response=requests.get(f'https://huggingface.co/Snowflake/snowflake-arctic-embed-m-long/resolve/{BACKEND}/{name}',timeout=90)
            response.raise_for_status()
            path.write_bytes(response.content)
        files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (ROOT/'backend_manifest.json').write_text(json.dumps({'revision':BACKEND,'sha256':files},indent=2))

def engine():
    import torch
    from transformers import AutoTokenizer
    from safetensors.torch import load_file
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    sys.path.insert(0,str(CACHE))
    from snowflake_cpu.configuration_hf_nomic_bert import NomicBertConfig
    from snowflake_cpu.modeling_hf_nomic_bert import NomicBertModel
    location=CACHE/'model'
    config=NomicBertConfig.from_json_file(str(location/'config.json'))
    config.use_flash_attn=False
    model=NomicBertModel(config,add_pooling_layer=False)
    state=load_file(str(location/'model.safetensors'))
    missing,unexpected=model.load_state_dict(state,strict=False)
    assert not missing and not unexpected, (missing,unexpected)
    model.eval()
    tokenizer=AutoTokenizer.from_pretrained(str(location),local_files_only=True)
    @torch.inference_mode()
    def encode(docs):
        batch=tokenizer(docs,max_length=1024,truncation=True,padding=True,return_tensors='pt')
        y=model(**batch)[0][:,0]
        return y.float().numpy()
    return encode
if __name__=='__main__':
    install_backend()
    encode=engine()
    print(encode(['Field symbols and internal basis.']).shape)

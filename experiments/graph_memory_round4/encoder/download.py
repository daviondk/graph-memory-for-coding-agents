"""Download the exact public author wrapper and model revision, without credentials."""
from pathlib import Path
import urllib.request
from common_run import D,hashfile

revision="5604afdc964f6c53782a6813140ade5216b99006"
repocommit="ccacd12a68783ca27e9997c3b754d3e9e0d958da"
(D/"weights").mkdir(exist_ok=True)
for name in ("config.json","merges.txt","vocab.json","special_tokens_map.json","tokenizer_config.json","README.md","pytorch_model.bin"):
    dst=D/"weights"/name
    if not dst.exists():
        urllib.request.urlretrieve("https://huggingface.co/microsoft/unixcoder-base/resolve/"+revision+"/"+name,dst)
assert hashfile(D/"weights/pytorch_model.bin")=="6732b60037b086557e4c731c3748c99b4fec735d9ffe3c4c70061fd142e6b9d9"
wrapper=D/"repo_unixcoder.py"
if not wrapper.exists():
    urllib.request.urlretrieve(f"https://raw.githubusercontent.com/Leolty/repobench/{repocommit}/model/unixcoder.py",wrapper)
print("model sha256 and wrapper",hashfile(D/"weights/pytorch_model.bin"),hashfile(wrapper))

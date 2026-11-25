"""Prepare a pinned released parser and byte-identical single-link copies of bundled data."""
from data import PRIVATE,sha
from pathlib import Path
from urllib.request import urlopen
import os
import shutil
import subprocess
def main():
    env=dict(os.environ,UV_CACHE_DIR=str(PRIVATE/'uv-cache'));venv=PRIVATE/'core-env';py=venv/'Scripts/python.exe';PRIVATE.mkdir(parents=True,exist_ok=True)
    if not py.exists():subprocess.run(['uv','venv','-p','3.12',str(venv)],env=env,check=True)
    subprocess.run(['uv','pip','install','--python',str(py),'llama-index-core==0.14.26','nltk==3.10.4'],env=env,check=True)
    core=venv/'Lib/site-packages/llama_index/core'
    source='llama-index-core/llama_index/core/node_parser/text/sentence_window.py'
    pin='0d4f96876cfe7e325f3c1b72ec5f5f580f173bb5';f=PRIVATE/'upstream'/source.replace('/','_');f.parent.mkdir(exist_ok=True)
    if not f.exists():
        with urlopen(f'https://raw.githubusercontent.com/run-llama/llama_index/{pin}/{source}',timeout=30) as r:f.write_bytes(r.read())
    assert sha(f)==sha(core/'node_parser/text/sentence_window.py')=='2615dc860bfac8edb67cb134cb136d76e2ba3a3e839a8baa9ba3c8b093812aef'
    for tag in ('corpora/stopwords','tokenizers/punkt_tab'):
        a=core/'_static/nltk_cache'/tag;b=PRIVATE/'bundled-nltk-copy'/tag
        shutil.copytree(a,b,dirs_exist_ok=True)
        for item in a.rglob('*'):
            if item.is_file():
                dest=b/item.relative_to(a);assert sha(item)==sha(dest) and dest.stat().st_nlink==1
if __name__=='__main__':main()

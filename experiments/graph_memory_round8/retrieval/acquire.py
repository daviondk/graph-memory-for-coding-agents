"""Fetch original author files and randomly accessible ZIP entries."""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import time
import zipfile
import zlib
import requests

ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("SWERANK_TEMP", "D:/CodexResearch/x20-r8-swerank-runtime"))
CACHE.mkdir(parents=True, exist_ok=True)
ARCHIVE = 'https://drive.usercontent.google.com/download?id=1pjWkpEfFRAts5hkcCGFSoBW1HiQQTsTo&export=download&confirm=t'
MODEL = 'Salesforce/SweRankEmbed-Small'
REV = '745d2a06103a66d3cfa600aa52fc0d3523010daa'
SOURCE = 'd3df5088485eda13c7eebfcd6250052fd276f1a3'
def ranged(lo,hi):
    for n in range(4):
        try:
            r=requests.get(ARCHIVE+'&rangeoffset='+str(lo), headers={'Range':f'bytes={lo}-{hi}'},timeout=90)
            r.raise_for_status()
            assert r.status_code==206 and len(r.content)==hi-lo+1, (r.status_code,len(r.content),lo,hi)
            return r.content
        except Exception:
            if n==3: raise
            time.sleep(2+n)
def index():
    path = CACHE/'archive-index'
    start=1060019204
    if not path.exists(): path.write_bytes(ranged(start,1061305745))
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as z:
        return {e.filename:(start+e.header_offset,e.compress_size,e.file_size,e.CRC,e.compress_type) for e in z.infolist()}
def member(name):
    entry=index()[name]
    digest=hashlib.sha256(name.encode()).hexdigest()
    path=CACHE/'members'/digest
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        pos,cs,fs,crc,cm=entry
        header=ranged(pos,pos+29)
        fn,extra=struct.unpack('<HH',header[26:30])
        data=ranged(pos+30+fn+extra,pos+30+fn+extra+cs-1)
        raw=zlib.decompress(data,-15) if cm==8 else data
        assert len(raw)==fs and zlib.crc32(raw)==crc
        path.write_bytes(raw)
    return path.read_bytes()
def model():
    out=CACHE/'model'
    out.mkdir(exist_ok=True)
    refs=requests.get(f'https://huggingface.co/api/models/{MODEL}/revision/{REV}?blobs=true',timeout=30).json()
    man={}
    for item in refs['siblings']:
        name=item['rfilename']
        if '/' in name or not name.endswith(('.json','.txt','.py','.safetensors')): continue
        p=out/name
        sha=item.get('lfs',{}).get('sha256')
        if not p.exists() or p.stat().st_size!=item['size']:
            with requests.get(f'https://huggingface.co/{MODEL}/resolve/{REV}/{name}?download=true',stream=True,timeout=180) as r:
                r.raise_for_status()
                with p.with_suffix('.part').open('wb') as target:
                    for b in r.iter_content(2**20): target.write(b)
            p.with_suffix('.part').replace(p)
        actual=hashlib.sha256(p.read_bytes()).hexdigest()
        if sha: assert sha==actual
        man[name]=dict(size=p.stat().st_size,sha256=actual)
    (ROOT/'model_manifest.json').write_text(json.dumps(man,indent=2))
    print(man.keys())
if __name__=='__main__':
    import sys
    if sys.argv[1]=='model': model()
    if sys.argv[1]=='index':
        idx=index()
        print(len(idx))
        print('\n'.join(k for k in list(idx)[:35]))
        print('\n'.join(k for k in idx if 'sympy__sympy' in k)[:1000])

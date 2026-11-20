"""Original SOSP 2023 revision, published score verification, and chronological suffix comparison."""
import gzip,json,os,re,subprocess,sys,tarfile,urllib.request
from pathlib import Path
import numpy as np
from fetch import RAW,HERE,fetch,digest
from study import RESULTS
from native import transport

REV="79fde46c03180b95b1091249a6f140282aeae333"
BASE="https://raw.githubusercontent.com/Thesys-lab/sosp23-s3fifo/"+REV+"/"
REF=BASE+"result/cachesim/MSR/hm_0.IQI.bin.txt"

def download():
    dst=RAW/"paper2023"
    with urllib.request.urlopen("https://codeload.github.com/Thesys-lab/sosp23-s3fifo/tar.gz/"+REV,timeout=100) as stream:
        with tarfile.open(fileobj=stream,mode="r|gz") as t:
            for r in t:
                rel=r.name.split("/")[1:]
                if r.isfile() and rel[:1]==["libCacheSim"]:
                    path=dst.joinpath(*rel)
                    assert path.resolve().is_relative_to(dst.resolve())
                    path.parent.mkdir(exist_ok=True,parents=True);path.write_bytes(t.extractfile(r).read())

def run():
    n=json.loads((RESULTS/"native.json").read_text());cap=n['cap'];cut=n['warm'];src=RAW/'native.stream'
    b=fetch(REF);published={}
    for row in b.decode().splitlines():
        m=re.search(r"\.zst\s+(S3FIFO|ARC|LRU) cache size\s+43918, 3993316 req, miss ratio ([\d.]+)",row)
        if m:published[m[1]]=m[2]
    assert len(published)==3
    cli=(RAW/'result'/'hm_native.zst').read_text()
    recent=(RAW/'native_cli.txt').read_text()
    out={'revision':REV,'published_url':REF,'published_file_sha256':digest(b),'author_results':published,'historical_cli_rows':cli.splitlines(),'current_cli_rows':recent.splitlines(),'methods':[]}
    for algo,official in [('s3','S3FIFO'),('arc','ARC'),('lru','LRU')]:
        flags=RAW/('legacy_'+algo+'.bin')
        p=subprocess.run(transport([RAW/'historical-driver',algo,str(cap),str(cut),src,flags]),capture_output=True,check=True)
        matched=re.search(r'n=(\d+) pre=(\d+) post=(\d+)',p.stdout.decode())
        tot,pre,post=map(int,matched.groups()); assert tot==n['records']
        row=np.fromfile(flags,'u1')
        assert int(row.sum())==post and len(row)==tot-cut
        bits=np.packbits(row,bitorder="little").tobytes()
        (RESULTS/('historical_'+algo+'.bits.gz')).write_bytes(gzip.compress(bits,mtime=0))
        assert f"{(post+pre)/tot:.4f}"==published[official]
        out['methods'].append(dict(algo=official,pre_misses=pre,post_misses=post,post_n=tot-cut,full_n=tot,full_misses=pre+post,full_mr=(pre+post)/tot,suffix_mr=post/(tot-cut),bits_sha256=digest(bits)))
    (RESULTS/'historical.json').write_text(json.dumps(out,indent=2),encoding="utf8")
    print(out['methods'])
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='download':download()
    else:run()

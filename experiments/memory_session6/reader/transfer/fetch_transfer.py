import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
from concurrent.futures import ThreadPoolExecutor
import requests

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'sources'
PAPER='https://raw.githubusercontent.com/iai-group/ecir2023-reproducibility/a92c2118557d61a65a2c85b3ad783c43c1740f12/'
CAST='https://raw.githubusercontent.com/daltonj/treccastweb/33846610b736da392efeab00e4c6f4519e0dacf1/2021/'
URLS={'topics.json':CAST+'2021_automatic_evaluation_topics_v1.0.json','qrels.txt':CAST+'trec-cast-qrels-docs.2021.qrel',
      'qrels_nist.txt':'https://trec.nist.gov/data/cast/trec-cast-qrels-docs.2021.qrel',
      'qrels_reproduction.txt':PAPER+'data/qrels/2021.txt'}
for arm in ['raw','automatic']:
    for ext in ['meta.yaml','trec.tar.gz']:
        name=f'{arm}_bm25_mono-t5_2021.{ext}'
        URLS[name]=PAPER+'data/runs/2021/'+name


def fetch(entry):
    name,url=entry
    p=SOURCE/name
    if not p.exists():
        r=requests.get(url,timeout=90)
        r.raise_for_status()
        p.write_bytes(r.content)
    raw=p.read_bytes()
    return name,{'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


if __name__=='__main__':
    SOURCE.mkdir(exist_ok=True)
    with ThreadPoolExecutor(5) as pool:
        receipt=dict(pool.map(fetch,URLS.items()))
    p=ROOT/'public_sources.json'
    if p.exists():
        assert json.loads(p.read_bytes())==receipt
    else:
        p.write_text(json.dumps(receipt,indent=2))
    assert (SOURCE/'qrels_nist.txt').read_text().split()==(SOURCE/'qrels.txt').read_text().split()
    for arm in ['raw','automatic']:
        with tarfile.open(SOURCE/f'{arm}_bm25_mono-t5_2021.trec.tar.gz') as tar:
            names=[m for m in tar.getmembers() if m.isfile() and m.name.endswith('.trec') and not m.name.split('/')[-1].startswith('._')]
            assert len(names)==1
            raw=tar.extractfile(names[0]).read()
            print(arm,raw.splitlines()[0],len(raw.splitlines()))
            (SOURCE/f'{arm}.run').write_bytes(raw)
    print('qrel format', (SOURCE/'qrels.txt').read_text().splitlines()[0])
    print('turn fields',list(json.loads((SOURCE/'topics.json').read_bytes())[0]['turn'][0]))

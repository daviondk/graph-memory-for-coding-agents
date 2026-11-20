"""Fetch pinned public CAsT text data and NIST trec_eval source, recording integrity."""
import hashlib
import io
import json
import pathlib
import requests
import zipfile
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / 'sources'
CAST = '33846610b736da392efeab00e4c6f4519e0dacf1'
TREC = 'd95ca64e14a47d763ae349fb65e6d8cde4141dbd'
BASE = f'https://raw.githubusercontent.com/daltonj/treccastweb/{CAST}/2020/'
URLS = {
    'topics.json': BASE + '2020_automatic_evaluation_topics_v1.0.json',
    'raw.run': BASE + 'baselines/y2_raw_results_500.v1.0.run',
    'auto.run': BASE + 'baselines/y2_automatic_results_500.v1.0.run',
    'qrels.txt': BASE + '2020qrels.txt',
    'nist_qrels.txt': 'https://trec.nist.gov/data/cast/2020qrels.txt',
    'trec_eval.zip': f'https://codeload.github.com/usnistgov/trec_eval/zip/{TREC}',
    'LICENSE_CAST.txt': BASE.replace('/2020/', '/LICENSE'),
}


def fetch(entry):
    name, url = entry
    path = DATA / name
    if not path.exists():
        with requests.get(url, timeout=90) as res:
            res.raise_for_status()
            path.write_bytes(res.content)
    buf = path.read_bytes()
    return name, {'url': url, 'sha256': hashlib.sha256(buf).hexdigest(), 'bytes': len(buf)}


if __name__ == '__main__':
    DATA.mkdir(exist_ok=True)
    with ThreadPoolExecutor(5) as pool:
        receipt = dict(pool.map(fetch, URLS.items()))
    assert (DATA/'qrels.txt').read_text().split() == (DATA/'nist_qrels.txt').read_text().split()
    lock = ROOT / 'source_receipt.json'
    if lock.exists():
        assert json.loads(lock.read_bytes()) == receipt
    else:
        lock.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    with zipfile.ZipFile(DATA / 'trec_eval.zip') as zf:
        for name in zf.namelist():
            assert (DATA / name).resolve().is_relative_to(DATA.resolve())
        zf.extractall(DATA)
    print('Verified official qrels, run files and pinned scorer', len(receipt))


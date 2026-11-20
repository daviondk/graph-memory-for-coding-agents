"""Fetch the additional pinned, public reference scripts and dialogue-variant data. No authentication required."""
import urllib.request,json,hashlib,concurrent.futures
from pathlib import Path
P=Path(__file__).resolve().parent/'upstream';P.mkdir(exist_ok=True)
prefix="https://raw.githubusercontent.com/"
files={
"snap-research/locomo/3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376/":{"task_eval/evaluation.py":"evaluation.py"},
"campaign-layer/memory-core/ffb105ee2c1c88609ad63f82c74082a8482e9ead/":{"bench/locomo/"+x:x for x in ["build_corpus.py","score_mode_a.ts","validate_evidence.py","DATA.md"]},
"MiuLab/LoCoMo-Conv/1925e924c36e632283ea91f2212157829f4e0e45/":{"README.md":"lc_README.md","data/locomo10_dialog.json":"lc_locomo10_dialog.json","data/locomo10_multimem_full.json":"lc_locomo10_multimem_full.json","retrieval/compute_retrieval_metrics.py":"lc_compute_retrieval_metrics.py"}}
def run(args):
    url,name=args;f=P/name;data=urllib.request.urlopen(url,timeout=35).read();f.write_bytes(data)
    return dict(name=name,url=url,sha256=hashlib.sha256(data).hexdigest(),size=len(data))
with concurrent.futures.ThreadPoolExecutor(4) as ex:records=list(ex.map(run,[(prefix+r+x,f) for r,items in files.items() for x,f in items.items()]))
(P/'extra_sources.json').write_text(json.dumps(records,indent=2),encoding="utf8")
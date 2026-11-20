"""Fetch and project E3 into predictor-only input and unobserved following-request objects."""
from pathlib import Path
from urllib.request import urlopen
import gzip
import json
from download import HF,GH,ROOT,sha
def main():
    sources={'qwen_tokenizer.json':'https://huggingface.co/Qwen/Qwen3.8-27B/resolve/37561816e66b5b9153b1b64c10968c18c1e6f4a0/tokenizer.json',
             'e3_score.py':GH+'harness/e3_score.py','chains.jsonl':HF+'e3/chains.jsonl'}
    inf={}
    for n,u in sources.items():
        f=ROOT/'source'/n
        if not f.exists():f.write_bytes(urlopen(u,timeout=120).read())
        inf[n]={'url':u,'sha256':sha(f.read_bytes()),'bytes':f.stat().st_size}
    expected={line.split()[1]:line.split()[0] for line in (ROOT/'source/SHA256SUMS.txt').read_text().splitlines()}
    assert inf['chains.jsonl']['sha256']==expected['e3/chains.jsonl']
    (ROOT/'followup_source.json').write_text(json.dumps(inf,indent=1),encoding='utf8')
    cols=set()
    with (ROOT/'source/chains.jsonl').open(encoding='utf8') as src,gzip.open(ROOT/'e3_prefixes.jsonl.gz','wt',encoding='utf8') as f,gzip.open(ROOT/'e3_labels.jsonl.gz','wt',encoding='utf8') as g:
        for i,ln in enumerate(src):
            r=json.loads(ln)
            for j,b in enumerate(r['per_k']):
                cols.update(b)
                f.write(json.dumps({'i':i,'j':j,'S':b['S_k']},ensure_ascii=False)+'\n')
                g.write(json.dumps({'i':i,'j':j,'sess':r['sess'],'client':r['client'],'k':b['k'],'atomsF':b['atomsF']},ensure_ascii=False)+'\n')
    print('boundary columns',sorted(cols))
if __name__=='__main__':main()


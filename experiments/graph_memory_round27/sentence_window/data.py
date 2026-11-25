from pathlib import Path
import hashlib
import gzip
import json
import os
D=Path(__file__).resolve().parent
WORK=D.parents[1]
PRIOR=WORK/'graph_memory_round26/directional_replication'
OLD=WORK/'graph_memory_round25/directional_open'
RAW=Path('D:/CodexResearch/x20-r25-squad/train-v1.1.json')
PRIVATE=Path('D:/CodexResearch/x20-r27-sentences')
TOK=Path('D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def save(p,obj):
    b=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()+b'\n'
    t=p.with_suffix(p.suffix+'.part');t.write_bytes(gzip.compress(b,mtime=0) if p.suffix=='.gz' else b);os.replace(t,p)
    return sha(p)
def freeze():
    p=D/'plan.json'
    rec={'protocol':sha(D/'PROTOCOL_RU.md'),'source':sha(RAW),'tokenizer':sha(TOK),'prior':{n:sha(PRIOR/n) for n in ('cohort.json.gz','choices-lock.json','read-lock.json','plan.json')},'seed':263117,'n':5304,'groups':442,'cap':256,'window':3,'library':'llama-index-core==0.14.26','github':'0d4f96876cfe7e325f3c1b72ec5f5f580f173bb5'}
    assert rec['source']=='3527663986b8295af4f7fcdff1ba1ff3f72d07d61a20f487cb238a6ef92fd955'
    if p.exists():assert rec==read(p)
    else:assert not (D/'forecast-seal.json').exists();save(p,rec)
def body(a):return '\n\n'.join(p['context'] for p in a['paragraphs'])
def querytexts(a):return {q['id']:q['question'] for p in a['paragraphs'] for q in p['qas']}
if __name__=='__main__':freeze()

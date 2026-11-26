"""Post-forecast duplicate audit against previously available public QA corpora."""
from io46 import *
from panel import norm,lines
from collections import defaultdict
import pyarrow.parquet as pq

def main():
    assert get(D/'answer-seal.json')['answer']==sha(D/'answers.json.gz')
    qids=set(get(D/'panel.json')['order']);forms={};components={}
    for r in lines(RAW):
        if r['id'] in qids:
            forms[r['id']]=norm(r['question'])
            components[r['id']]={norm(z['question']) for z in r['question_decomposition']}
    pools={};hashes={}
    for name,src in [('2Wiki-dev',Path('D:/CodexResearch/x20-r32-2wiki/dev.parquet')),
                     ('Hotpot-validation',Path('D:/CodexResearch/x20-r31-hotpot/validation.parquet'))]:
        pools[name]={norm(x) for chunk in pq.ParquetFile(src).iter_batches(columns=['question']) for x in chunk.column(0).to_pylist()}
        hashes[name]=sha(src)
    p=Path('D:/CodexResearch/x20-r25-qasper/qasper-test-v0.3.json')
    pools['QASPER-test']={norm(item['question']) for row in get(p).values() for item in row['qas']};hashes['QASPER-test']=sha(p)
    for tag in ('train','dev'):
        p=Path(f'D:/CodexResearch/x20-r25-squad/{tag}-v1.1.json')
        pools['SQuAD-'+tag]={norm(item['question']) for row in get(p)['data'] for v in row['paragraphs'] for item in v['qas']}
        hashes['SQuAD-'+tag]=sha(p)
    pools['MuSiQue-dev']={norm(r['question']) for r in lines(DEV)};hashes['MuSiQue-dev']=sha(DEV)
    summary={k:dict(reference_forms=len(ref),whole_questions=sum(v in ref for v in forms.values()),
        questions_with_component_match=sum(bool(parts&ref) for parts in components.values())) for k,ref in pools.items()}
    put(D/'overlap.json',dict(n=len(forms),counts=summary,sources=hashes,answers=sha(D/'answer-seal.json')))
    print(summary)

if __name__=='__main__':main()

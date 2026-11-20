"""Prepare whitelisted pre-answer metadata, then join outcome pairs in a separate step."""
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parents[1]/'literature'
FEATURES=['disagreement','year2_minus_year1','max_minus_year1','year_span','distinct_years','first_max_position','question_words']


def load(path):
    with gzip.open(path,'rt',encoding='utf8') as f:
        return [json.loads(l) for l in f]


def keyed_meta():
    # Only these fields leave the source projections. Candidate text and answer keys never enter a feature.
    inp=SOURCE/'inputs'
    questions={r['query_id']:(r['question'],r['relation']) for r in load(inp/'queries_anchored_test.jsonl.gz')}
    subjects={r['query_id']:r['fact_key'].rsplit('_',1)[0] for r in load(inp/'key_anchored_test.jsonl.gz')}
    years={r['id']:r['year'] for r in load(inp/'statements_anchored_test.jsonl.gz')}
    ranks={}
    for name in ['cosine','time_rerank']:
        ranks[name]={r['query_id']:r['ranking'][:5] for r in load(inp/f'sub_anchored_test_{name}.jsonl.gz')}
    assert set(questions)==set(subjects)==set(ranks['cosine'])==set(ranks['time_rerank'])
    out={}
    for q,(question,rel) in questions.items():
        c,t=[ranks[a][q] for a in ['cosine','time_rerank']]
        assert len(set(c))==5 and set(c)==set(t) and c[2:]==t[2:]
        y=[years[doc] for doc in c]
        feat=[int(c[0]!=t[0]),y[1]-y[0],max(y)-y[0],max(y)-min(y),len(set(y)),y.index(max(y))+1,
              len(re.findall(r'[A-Za-z0-9_]+',question))]
        out[q]=dict(id=q,subject=subjects[q],relation=rel,features=feat,grades={})
    return out


if __name__=='__main__':
    joined=keyed_meta()
    raw=load(SOURCE/'paired_scores.jsonl.gz')
    for r in raw:
        item=joined[r['query']]
        assert r['relation']==item['relation'] and bool(item['features'][0])==r['dated']
        assert r['reader'] not in item['grades']
        item['grades'][r['reader']]=[r['plain'],r['with_dates']]
    assert all(len(v['grades'])==2 for v in joined.values())
    data=''.join(json.dumps(r,separators=(',',':'))+'\n' for r in joined.values()).encode()
    out=ROOT/'inputs.jsonl'
    if out.exists():assert out.read_bytes()==data
    else:out.write_bytes(data)
    print('Rows',len(joined),'readers',list(next(iter(joined.values()))['grades']),'sha256',hashlib.sha256(data).hexdigest())

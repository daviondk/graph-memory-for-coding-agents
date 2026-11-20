"""Rank the confidence of one fixed candidate using the current issue and prior records."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parent
T=ROOT.parent/'transfer'
sys.path.insert(0,str(T))
from prepare import load_inputs
from rank import words,edit_words,lexical

def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def save(n,x):(ROOT/n).write_text(json.dumps(x,indent=1,ensure_ascii=False)+'\n',encoding='utf8')
# Recognize filenames, dotted names, mixed-case and snake_case symbols. Names must occur in both records.
SYMBOL=re.compile(r'(?<![\w])(?:[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+|[A-Za-z]\w*_[A-Za-z0-9_]\w*|[a-z][A-Za-z0-9]*[A-Z]\w*|[A-Z][a-z0-9]+[A-Z]\w*)(?![\w])')
def symbols(ws):
    return set(SYMBOL.findall(' '.join(ws)))
def bm25(docs,query):
    lengths=[sum(d.values()) for d in docs]
    avg=sum(lengths)/len(docs) or 1
    df=Counter(t for d in docs for t in query.keys() & d.keys())
    return [math.fsum(min(q,2)*math.log1p((len(docs)-df[t]+.5)/(df[t]+.5))*d[t]*2.2/(d[t]+1.2*(.25+.75*length/avg)) for t,q in query.items() if t in d) for d,length in zip(docs,lengths)]
def main():
    docs,queries,meta=load_inputs()
    cards={}
    for key,d in docs.items():
        before=words(d['problem_statement'],192)
        edits=edit_words(d['patch'])
        cards[key]=(lexical(before+edits),symbols(before),symbols(edits))
    with gzip.open(T/'blind_ranks.jsonl.gz','rt',encoding='utf8') as f:prior=[json.loads(line) for line in f]
    rows=[]
    for x in prior:
        if x['scope']!='repo_time':continue
        k=x['target'];rank=x['ranks']['card'];q=words(queries[k]['problem_statement'],280)
        row={'id':k,'repo':x['repo'],'candidate':rank[0] if rank else None,'pool':len(rank),'hash':sha('delivery-budget|'+k),'bm25':0,'margin':0,'symbol':0,'issue_matches':[],'edit_matches':[],'gate':False}
        if rank:
            selected=cards[rank[0]]
            s=bm25([cards[i][0] for i in rank],lexical(q))
            overlaps=symbols(q)
            ia=overlaps & selected[1];ea=overlaps & selected[2]
            df=Counter(v for i in rank for v in (cards[i][1]|cards[i][2]) & (ia|ea))
            score=sorted(((2 if t in ea else 1)*math.log((len(rank)+1)/(df[t]+.5)) for t in ia|ea),reverse=True)
            row.update(bm25=s[0],margin=s[0]-max(s[1:]) if len(s)>1 else 0,symbol=sum(score[:3]),issue_matches=sorted(ia),edit_matches=sorted(ea),gate=bool(ea or len(ia)>=2))
        rows.append(row)
    active=[r for r in rows if r['candidate']]
    for m in ['bm25','margin','symbol']:
        ranked=sorted(active,key=lambda r:(-r[m],r['hash']))
        for b in [25,50,75]:
            selected={r['id'] for r in ranked[:math.ceil(len(ranked)*b/100)]}
            for r in rows:r[f'{m}_{b}']=r['id'] in selected
    assert len(rows)==258
    save('blind.json',rows)
    files=[ROOT/'predict.py',ROOT/'PROTOCOL.md',ROOT/'blind.json',T/'blind_ranks.jsonl.gz',T/'rank.py',T/'prepare.py']
    save('lock.json',{'sha256':{a.name:hashlib.sha256(a.read_bytes()).hexdigest() for a in files},'source_data':meta['raw_releases']})
    print(len(rows),len(active),'assessments locked')
if __name__=='__main__':main()


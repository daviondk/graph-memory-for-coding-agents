"""Select by salted ID hash; project only reader-visible fields from the public records."""
from io46 import *
import heapq,re,unicodedata
from collections import Counter
def norm(s):
    return ' '.join(re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',s).casefold()))
def lines(path):
    with path.open(encoding='utf8') as fp:
        for line in fp:yield json.loads(line)
def main():
    p=get(D/'plan.json');assert p['protocol']==sha(D/'PROTOCOL_RU.md') and p['raw']==sha(RAW) and p['dev']==sha(DEV)
    prior=get(W/'graph_memory_round33/musique_answers/predictions.json.gz')
    drows=list(lines(DEV));dq={norm(r['question']) for r in drows};di={r['id'] for r in drows}
    assert di==set(prior) and len(di)==2417
    ddocs={hexb((p['title']+'\0'+p['paragraph_text']).encode()) for r in drows for p in r['paragraphs']}
    by={};seen=set();counts=Counter()
    for r in lines(RAW):
        q=r['id'];key=norm(r['question']);assert q not in seen;seen.add(q);counts['source']+=1
        if q in di or key in dq:counts['duplicate_dev']+=1;continue
        digest=hexb(('r46-mq-panel-v1|'+q).encode())
        if key in by:counts['duplicate_train_question']+=1
        if key not in by or digest<by[key][0]:by[key]=(digest,q)
    ordered=[q for _,q in heapq.nsmallest(p['n'],by.values())];select=set(ordered);view={}
    for r in lines(RAW):
        q=r['id']
        if q not in select:continue
        docs=[[x['idx'],x['title'],x['paragraph_text']] for x in r['paragraphs']]
        assert len({x[0] for x in docs})==len(docs)>1
        view[q]=[r['question'],docs]
    assert set(view)==select and not (set(view)&di) and not ({norm(x[0]) for x in view.values()}&dq)
    put(PRIVATE/'visible.json.gz',view)
    put(D/'panel.json',dict(order=ordered,counts=counts,eligible=len(by),seen_dev=sorted(ddocs),
        observations=sha(PRIVATE/'visible.json.gz'),plan=sha(D/'plan.json'),code=sha(D/'panel.py')))
if __name__=='__main__':main()

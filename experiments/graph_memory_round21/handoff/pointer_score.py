import argparse
import gzip
import json
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from score import contrast, h

ROOT=Path(__file__).resolve().parent
CACHE=Path('D:/CodexResearch/x20-wikicontradict')


def evaluate():
    seal=json.loads((ROOT/'pointer-forecast-lock.json').read_text())
    inputs=json.loads((ROOT/'pointer-input-lock.json').read_text())
    predictions=ROOT/'pointer-forecasts.jsonl.gz'
    assert seal['selector']==h(ROOT/'pointer_predict.py') and seal['forecasts']==h(predictions) and seal['protocol']==h(ROOT/'pointer-protocol.json')
    cases={}
    for name,f in [('wiki','gold.json'),('rag','rag-gold.json')]:
        assert h(CACHE/f)==inputs['evaluator_sha'][name]
        labels=json.loads((CACHE/f).read_text(encoding='utf8'))
        cases[name]={v['case']:v for v in labels if (v['different'] and len(set(v['gold']))==2 if name=='wiki' else v['eligible'])}
    groups=defaultdict(lambda:defaultdict(dict))
    with gzip.open(predictions,'rt') as f:
        for line in f:
            r=json.loads(line)
            source=r['source']
            if r['case'] not in cases[source]: continue
            gold=cases[source][r['case']]
            first,alt=(gold['gold'],gold['gold']) if source=='wiki' else (gold['pair'],gold['alternative'])
            ids=set(sum(r['ids'],[]))
            anypair=bool(set(first)<=ids or set(alt)<=ids)
            assert r['used']==sum(r['bytes'].values())<=r['budget']
            groups[(source,r['budget'],r['limit'])][r['case']][r['policy']]=dict(both=int(anypair),first=int(set(first)<=ids),used=r['used'],rpc=r['bytes'],fetch=sum(len(a) for a in r['ids']),switch=r['best']!=[0,0])
    output={}
    for (src,b,lim),rec in sorted(groups.items()):
        clusters={k:v['article'] for k,v in cases[src].items()}
        summaries={}
        for method in next(iter(rec.values())):
            rr=[m[method] for m in rec.values()]
            channels=Counter()
            for i in rr: channels.update(i['rpc'])
            summaries[method]=dict(any_pair=sum(x['both'] for x in rr),canonical_pair=sum(x['first'] for x in rr),mean_bytes=np.mean([x['used'] for x in rr]),mean_bytes_by_opcode={k:v/len(rr) for k,v in sorted(channels.items())},mean_sql_body_fetches=np.mean([x['fetch'] for x in rr]),changed_nominee=sum(x['switch'] for x in rr))
        diffs={a+' minus '+b1:contrast(rec,a,b1,clusters) for a,b1 in [('paired','schema_e5'),('paired','length_e5'),('paired','shuffled'),('schema_e5','length_e5')]}
        output[f'{src}|{b}|{lim}']=dict(n=len(rec),clusters=len(set(clusters.values())),methods=summaries,contrasts=diffs)
    (ROOT/'pointer-results.json').write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    for name in ('wiki|1536|fill','rag|512|one'):
        rec=output[name]
        print(name,rec['n'],rec['clusters'],dict((m,v['any_pair']) for m,v in rec['methods'].items()),rec['contrasts']['paired minus length_e5'])


if __name__=='__main__': evaluate()


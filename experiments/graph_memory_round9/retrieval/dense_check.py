"""Independent single-document inference verifies published checkpoint scores."""
import json
import numpy as np
from source import ROOT,load_json,write_json,member,base,inputs,h
from encoder import engine,PREFIX
def main():
    sample=load_json(ROOT/'sample.json')['selected']
    # First task in each stratum by frozen sample order, without referring to judgments.
    tasks=list(dict.fromkeys(r['band'] for r in sample))
    enc=engine();out=[]
    for band in tasks:
        t=next(r['issue'] for r in sample if r['band']==band)
        ranking=load_json(ROOT/'dense'/(t+'.json'))['candidates']
        refs={r['id']:r['dot'] for r in ranking}
        ids=sorted(refs,key=lambda x:h('r9-numeric-check|'+x))[:3]
        docs={r['_id']:r['text'] for r in (json.loads(x) for x in member(base(t)+'corpus.jsonl').splitlines())}
        q=enc([PREFIX+inputs(t)[0]])[0]
        for s in ids:
            actual=float(q@enc([docs[s]])[0]);expected=refs[s]
            out.append({'issue':t,'function':s,'old':expected,'single_doc':actual,'abs_diff':abs(actual-expected)})
            assert np.isclose(actual,expected,rtol=0.0001,atol=0.001)
    write_json(ROOT/'encoder_check.json',out);print('9 scores max abs error',max(c['abs_diff'] for c in out))
if __name__=='__main__':main()

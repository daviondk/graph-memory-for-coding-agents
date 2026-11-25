"""Independent reconstruction of all rendered bills, source hits and primary confidence bounds."""
import json
import gzip
import hashlib
import os
from pathlib import Path
from collections import defaultdict
from tokenizers import Tokenizer
import numpy as np
os.environ['RAYON_NUM_THREADS']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
D=Path(__file__).resolve().parent;R=D.parents[1]/'graph_memory_round26/directional_replication'
def rd(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def union(arr):
    out=[]
    for a,b in sorted(arr):
        if b<=a:continue
        if out and a<=out[-1][1]:out[-1]=(out[-1][0],max(b,out[-1][1]))
        else:out.append((a,b))
    return out
def run():
    tok=Tokenizer.from_file('D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json');plan=rd(D/'plan.json')
    seal=rd(D/'forecast-seal.json');rec=rd(D/'results.json');mets=rd(D/'outcomes.json.gz');idx=rd(D/'sentence-index.json.gz')
    assert rec['rows']==sha(D/'outcomes.json.gz') and rec['forecast']==sha(D/'forecast-seal.json')
    assert len(mets)==5304 and len(idx)==442
    met={m['q']:m for m in mets};docs={};spans={}
    for a in rd(Path('D:/CodexResearch/x20-r25-squad/train-v1.1.json'))['data']:
        t=a['title']
        if t not in idx:continue
        src='\n\n'.join(p['context'] for p in a['paragraphs']);docs[t]=src
        pieces=idx[t]['s'];hashes=hashlib.sha256()
        for j in range(len(pieces)):
            raw=' '.join(src[l:h] for l,h in pieces[max(0,j-3):j+4])
            hashes.update(hashlib.sha256(raw.encode()).digest())
        assert hashes.hexdigest()==idx[t]['windows']
        offset=0
        for p in a['paragraphs']:
            for q in p['qas']:
                if q['id'] not in met:continue
                spans[q['id']]=[(offset+ans['answer_start'],offset+ans['answer_start']+len(ans['text'])) for ans in q['answers'] if ans['text'] and p['context'][ans['answer_start']:ans['answer_start']+len(ans['text'])]==ans['text']]
            offset+=len(p['context'])+2
    assert set(spans)==set(met)
    checked=paid_pairs=0;votes=defaultdict(list)
    for i,(name,h) in enumerate(seal['files']):
        assert sha(D/name)==h;chunk=rd(D/name);choices=rd(R/f'choices-{i}.json.gz')
        assert chunk.keys()==choices.keys()
        for q,z in chunk.items():
            s=docs[z['t']];original=choices[q];visible=union([(l,h) for e,l,h in original['base']]);v=met[q];extra={}
            for key,(parts,price) in z['profiles'].items():
                wire=''.join(f'[0:{x[1]}] ' if x[0]=='h' else (s[x[1]:x[2]] if x[0]=='s' else ('\n' if x[0]=='n' else ' ')) for x in parts)
                assert len(tok.encode(wire,add_special_tokens=False).ids)==price<=256
                opened=union([(p[1],p[2]) for p in parts if p[0]=='s'])
                allsp=union(visible+opened)
                cv=max(sum(max(0,min(y,h)-max(x,l)) for x,y in allsp)/(h-l) for l,h in spans[q])
                overlap=sum(max(0,min(y,b)-max(x,a)) for x,y in opened for a,b in visible)
                extra[key]=[int(cv==1),cv,price,overlap,sum(y-x for x,y in opened),sum(p[0]=='h' for p in parts)]
            for method,k in z['online'].items():
                assert extra[k]==v['online'][method]
                if method=='boundary_window':assert extra[k][3]==0
                checked+=1
            for method,(aa,bb) in z['equal'].items():
                assert extra[aa][2]==extra[bb][2] and [extra[aa],extra[bb]]==v['equal'][method]
                if method=='boundary_window':
                    assert extra[bb][3]==0;votes[z['t']].append(extra[aa][0]-extra[bb][0])
                checked+=2;paid_pairs+=1
    ts=sorted(votes);n=np.array([len(votes[t]) for t in ts]);delta=np.array([sum(votes[t]) for t in ts])
    rng=np.random.default_rng(263117);boots=[]
    for _ in range(200):
        ids=rng.integers(len(ts),size=(100,len(ts)));boots.extend(100*delta[ids].sum(axis=1)/n[ids].sum(axis=1))
    pr=rec['full_panel']['boundary_window-equal'];assert np.allclose(np.quantile(boots,[.025,.975]),pr['cluster95_pp'],atol=1e-12,rtol=0)
    assert abs(100*delta.sum()/n.sum()-pr['change_pp'])<1e-12
    out={'questions':len(met),'articles':len(ts),'native_windows':sum(len(v['s']) for v in idx.values()),'individual_outcomes':checked,'equal_pairs':paid_pairs,'primary_ci':pr['cluster95_pp'],'source':sha(Path(__file__)),'results':sha(D/'results.json'),'predictions':sha(D/'forecast-seal.json')}
    (D/'verified.json').write_text(json.dumps(out,sort_keys=True,separators=(',',':')),encoding='utf-8')
    print(out)
if __name__=='__main__':run()

"""CPU retrieval. Reads only pre-sanitized, label-free text files."""
import collections
import gc
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer, AutoModelForSequenceClassification

ROOT = Path(__file__).resolve().parent
ENC = os.environ.get('CONTRIEVER_PATH','D:/CodexResearch/x20-longmemeval-dretr/contriever')
CE = os.environ.get('MINILM_PATH','D:/CodexResearch/x20-boundary-rerank/model')
torch.set_num_threads(3)
torch.set_num_interop_threads(1)


def terms(text):
    result = []
    for term in re.findall(r'[A-Za-z0-9_]+',text):
        result.append(term.lower())
        parts = re.sub(r'([a-z])([A-Z])',r'\1 \2',term).replace('_',' ').lower().split()
        if len(parts)>1:
            result.extend(parts)
    return result


def bm25(docs, queries):
    docs = [collections.Counter(terms(d)) for d in docs]
    freq = collections.Counter(t for d in docs for t in d)
    lengths = np.array([d.total() for d in docs])
    avg = max(1,lengths.mean())
    out = np.zeros((len(queries),len(docs)))
    for qi,q in enumerate(queries):
        counts = collections.Counter(terms(q))
        for t,n in counts.items():
            df = freq[t]
            if df:
                tf = np.array([d[t] for d in docs])
                out[qi] += min(2,n)*math.log((len(docs)+1)/(df+.5)) * (2.2*tf)/(tf+1.2*(.25+.75*lengths/avg))
    return out


def encode(texts, model, tok):
    result = []
    with torch.inference_mode():
        for i in range(0,len(texts),6):
            x=tok(texts[i:i+6],truncation=True,max_length=384,padding=True,return_tensors='pt')
            hid=model(**x).last_hidden_state
            vec=(hid*x.attention_mask.unsqueeze(-1)).sum(1)/x.attention_mask.sum(1,keepdim=True)
            result.extend(torch.nn.functional.normalize(vec,dim=1).numpy())
    return np.stack(result)


def ranks(scores):
    return np.argsort(-scores,axis=1,kind='stable')


def reciprocal(scores):
    return 1/(13+np.argsort(ranks(scores),axis=1))


def dump(name,obj):
    p=ROOT/name
    p.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf8')
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run():
    start=time.time()
    cards=json.loads((ROOT/'cards.json').read_text(encoding='utf8'))
    rows=json.loads((ROOT/'queries.json').read_text(encoding='utf8'))
    qs=[r['query'] for r in rows]
    fields={f:[c[f] for c in cards] for f in ('symptom','closure','edits')}
    fields['flat']=[' '.join(c[f] for f in ('symptom','edits','closure')) for c in cards]
    fields['outcome']=[c['closure']+' '+c['edits'] for c in cards]
    scores={f:bm25(v,qs) for f,v in fields.items()}
    sparse=2*reciprocal(scores['symptom'])+reciprocal(scores['closure'])+reciprocal(scores['edits'])
    t1=time.time()
    model=AutoModel.from_pretrained(ENC,local_files_only=True).eval()
    tok=AutoTokenizer.from_pretrained(ENC,local_files_only=True)
    qvec=encode(qs,model,tok)
    dense={}
    for f in ('flat','symptom','closure'):
        dense[f]=qvec@encode(fields[f],model,tok).T
    del model,tok
    gc.collect()
    t2=time.time()
    fusion=sparse+2*reciprocal(dense['symptom'])+reciprocal(dense['closure'])
    arr={'bm25_flat':ranks(scores['flat']),'bm25_symptom':ranks(scores['symptom']),'bm25_outcome':ranks(scores['outcome']),'dense_flat':ranks(dense['flat']),'sparse_fields':ranks(sparse),'fusion':ranks(fusion)}
    ce=AutoModelForSequenceClassification.from_pretrained(CE,local_files_only=True).eval()
    ctok=AutoTokenizer.from_pretrained(CE,local_files_only=True)
    order=arr['fusion'].copy()
    with torch.inference_mode():
        for qi,q in enumerate(qs):
            top=order[qi,:5].copy()
            x=ctok([q]*5,[fields['flat'][i] for i in top],truncation=True,max_length=512,padding=True,return_tensors='pt')
            values=ce(**x).logits[:,0].numpy()
            order[qi,:5]=top[np.argsort(-values,kind='stable')]
    arr['minilm']=order
    out=[{'ordinal':qi,**{name:[cards[j]['key'] for j in a[qi,:10]] for name,a in arr.items()}} for qi in range(len(qs))]
    sha=dump('blind_ranks.json',out)
    dump('rank_run.json',{'ranks_sha256':sha,'sparse_seconds':t1-start,'encode_seconds':t2-t1,'ce_seconds':time.time()-t2,'threads':3,'torch':torch.__version__,'top_stored':10,'rows':len(out),'cpu':True,'enc':ENC,'ce':CE})
    print(sha, len(out),round(time.time()-start),flush=True)


if __name__=='__main__':
    run()


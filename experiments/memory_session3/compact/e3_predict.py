"""Carry a bounded typed record from older production summaries across later compactions."""
from collections import defaultdict
import gzip
import json
import math
import time
from predict import ROOT,author,TYPES,dumps,sha_bytes
from token_predict import fit,token_count,TOK
def middle(s,cap):
    ids=TOK.encode(s,add_special_tokens=False).ids
    if len(ids)<=cap:return s
    if cap<=0:return ''
    a=max(0,cap-2)
    while a>=0:
        h=(2*a)//3; t=a-h
        out=(TOK.decode(ids[:h],skip_special_tokens=False) if h else '')+'\n…\n'+(TOK.decode(ids[-t:],skip_special_tokens=False) if t else '')
        if token_count(out)<=cap:return out
        a-=1
    return ''
def add(core,extra,cap):
    if not extra:return core
    corecap=cap-token_count(extra)-1
    while corecap>=0:
        body=middle(core,corecap)
        out=body+'\n'+extra if body else extra
        if token_count(out)<=cap:return out
        corecap-=1
    return ''
def recent_extras(previous,current):
    known=set();out=[]
    for source in reversed(previous):
        d=author.atoms_in_text(source)
        cats=[[(k,v) for v in sorted(d.get(k,[]))] for k in TYPES]
        for i in range(max((len(x) for x in cats),default=0)):
            for ls in cats:
                if i>=len(ls):continue
                a=ls[i]
                if a not in known and a[1] not in current:
                    out.append(a);known.add(a)
    return out
def main():
    previous=defaultdict(list);counts=0;start=time.perf_counter()
    with gzip.open(ROOT/'e3_prefixes.jsonl.gz','rt',encoding='utf8') as reader,gzip.open(ROOT/'e3_predictions.jsonl.gz','wt',encoding='utf8') as f:
        for line in reader:
            r=json.loads(line);prev=previous[r['i']];assert len(prev)==r['j']
            s=r['S'];cap=token_count(s)
            candidates=recent_extras(prev,s)
            _,extra=fit(candidates,cap//10,token_count,True)
            actual=token_count(extra)
            raw=''
            if prev and actual:
                ids=TOK.encode(prev[-1],add_special_tokens=False).ids
                raw=TOK.decode(ids[-actual:],skip_special_tokens=False)
                while token_count(raw)>actual:raw=raw[1:]
            outputs={'production':s,'sidecar_fixed':add(s,extra,cap),'raw_fixed':add(s,raw,cap),
                     'core_only':middle(s,cap-actual-1) if extra else s,'sidecar_extra':add(s,extra,cap+cap//10)}
            for k,text in outputs.items():
                used=token_count(text)
                assert used <= (cap+cap//10 if k=='sidecar_extra' else cap)
                f.write(dumps({'i':r['i'],'j':r['j'],'arm':k,'S':text,'used':used,'available':actual,'base':cap})+'\n')
            prev.append(s);counts+=1
    files=['e3_predictions.jsonl.gz','e3_predict.py','token_predict.py','e3_prefixes.jsonl.gz','TOKEN_AND_TRACE_PROTOCOL.md','source/qwen_tokenizer.json']
    (ROOT/'e3_lock.json').write_text(json.dumps({'sha256':{n:sha_bytes((ROOT/n).read_bytes()) for n in files},'n':counts,'wall_s':time.perf_counter()-start},indent=1),encoding='utf8')
if __name__=='__main__':main()


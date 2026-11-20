"""Qwen-token and UTF-8 caps for E2 anchors. Predictions have no access to future actions/labels."""
from collections import defaultdict
from pathlib import Path
from functools import lru_cache
import gzip
import hashlib
import json
import sys
import time
from tokenizers import Tokenizer
from predict import features,ROOT,dumps,sha_bytes
TOK=Tokenizer.from_file(str(ROOT/'source/qwen_tokenizer.json'))
def token_count(s):return len(TOK.encode(s,add_special_tokens=False).ids)
def byte_count(s):return len(s.encode())
def fmt(items,grouped):
    if not grouped:return '\n'.join(f'- {k}: {v}' for k,v in items)
    g=defaultdict(list)
    for k,v in items:g[k].append(v)
    return '\n'.join(line for k,vs in g.items() for line in [f'[{k}]',*vs])
def fit(order,cap,size,grouped,fixed=False):
    if not order:return [],''
    # Find the long prefix that fits. Thereafter check all remaining candidates individually.
    low=0;high=len(order)
    while low<high:
        mid=(low+high+1)//2
        if size(fmt(order[:mid],grouped))<=cap:low=mid
        else:high=mid-1
    selected=order[:low]
    for a in order[low:]:
        if fixed:break
        candidate=selected+[a]
        if size(fmt(candidate,grouped))<=cap:selected=candidate
    S=fmt(selected,grouped)
    assert size(S)<=cap
    return selected,S
def propose(i,h,endpoint):
    raw,official,auth,orders=features(h)
    for cost,size in [('token',token_count),('byte',byte_count)]:
        if endpoint=='future' and cost=='byte':continue
        cap=size(official)
        memory={'author_index':(auth,official)}
        compressed=fmt(auth,True)
        # Extremely small outputs can cost extra as headers; return to original representation for fixed-set fairness.
        memory['same_items_grouped']=(auth,compressed if size(compressed)<=cap else official)
        data={'author_fill_lines':(orders['author_grouped'],False),'author_fill_grouped':(orders['author_grouped'],True),
              'round_robin':(orders['round_robin'],True),'frequency':(orders['frequency'],True),'witness_grouped':(orders['witness_grouped'],True)}
        for arm,(ord_,grouped) in data.items():memory[arm]=fit(ord_,cap,size,grouped)
        for arm,(items,S) in memory.items():
            yield {'endpoint':endpoint,'cost':cost,'i':i,'arm':arm,'S':S,'items':items,'cap':cap,'used':size(S),'tokens':token_count(S),'bytes':byte_count(S)}
def main():
    start=time.perf_counter();cpu=time.process_time()
    with gzip.open(ROOT/'histories.jsonl.gz','rt',encoding='utf8') as src,gzip.open(ROOT/'token_predictions.jsonl.gz','wt',encoding='utf8',compresslevel=4) as f:
        for line in src:
            x=json.loads(line);h=x['H'];i=x['i']
            for endpoint,hist in [('official',h),('future',h[:(3*len(h))//4])]:
                for pred in propose(i,hist,endpoint):f.write(dumps(pred)+'\n')
    files=['token_predictions.jsonl.gz','token_predict.py','predict.py','TOKEN_AND_TRACE_PROTOCOL.md','source/qwen_tokenizer.json','histories.jsonl.gz','followup_source.json']
    lock={n:sha_bytes((ROOT/n).read_bytes()) for n in files}
    (ROOT/'token_lock.json').write_text(json.dumps({'sha256':lock,'wall_s':time.perf_counter()-start,'cpu_s':time.process_time()-cpu},indent=1),encoding='utf8')
if __name__=='__main__':main()


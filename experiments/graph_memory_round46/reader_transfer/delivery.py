"""Decode exactly the two transmitted document slices, without gold or model completions."""
from functools import lru_cache
from io46 import *
from engine import enc,post

@lru_cache(maxsize=10000)
def decode(seq):
    return post('/detokenize',{'tokens':list(seq)})['content']

def main():
    frozen=get(D/'input-seal.json')
    assert sha(D/'contexts.json.gz')==frozen['contexts'] and sha(D/'prompts.json.gz')==frozen['prompts']
    prompts=get(D/'prompts.json.gz');ctx=get(D/'contexts.json.gz')
    end=enc('<|im_end|>\n<|im_start|>assistant\n',True);sep=enc('\nDocument 2:\n')
    doc1=enc('\nDocument 1:\n');out={}
    for q,r in ctx.items():
        for a in ARMS:
            _,k,n=r['prompt'][a]
            if k in out:continue
            s=prompts[k];assert s[-len(end):]==end and len(s)==n
            b=n-len(end)-r['second_tokens'];v=b-len(sep);u=v-r['first_tokens']
            assert s[v:b]==sep and s[u-len(doc1):u]==doc1
            out[k]=[decode(tuple(s[u:v])),decode(tuple(s[b:-len(end)]))]
    put(PRIVATE/'delivered-text.json.gz',out);put(D/'delivery-seal.json',dict(
        contexts=sha(D/'input-seal.json'),text=sha(PRIVATE/'delivered-text.json.gz'),unique=len(out),code=sha(D/'delivery.py')))

if __name__=='__main__':main()

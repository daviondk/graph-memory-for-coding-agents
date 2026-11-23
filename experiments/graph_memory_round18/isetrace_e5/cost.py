"""Account for the truncated inputs and 64-wide padding that the frozen encoder receives."""
import hashlib,sqlite3,time
import numpy as np
from transformers import AutoTokenizer
from project import W,CACHE,ROOT,put,load
def main():
    tok=AutoTokenizer.from_pretrained(str(W),local_files_only=True,use_fast=True)
    con=sqlite3.connect(CACHE/'vectors.sqlite3',timeout=90)
    cur=con.execute('select text from corpus order by nchar,k');n=0;tokens=padded=0;dq=0
    digest=hashlib.sha256()
    while block:=cur.fetchmany(512):
        ss=[e[0] for e in block];nx=np.argsort([-len(x) for x in ss]);n+=len(ss)
        lens=tok([ss[j] for j in nx],padding=False,truncation=True,max_length=512,return_length=True,verbose=False)['length']
        for ll in lens:digest.update(int(ll).to_bytes(2,'little'))
        tokens+=sum(lens);dq+=sum(t.startswith('query: ') for t in ss)
        for i in range(0,len(lens),64):padded+=len(lens[i:i+64])*max(lens[i:i+64])
    assert n==load(ROOT/'inventory.json')['unique_prefixed_strings']
    put(ROOT/'token-cost.json',dict(unique_prefixed_inputs=n,unique_queries_by_prefix=dq,native_tokenizer=str(type(tok).__name__),max_sequence_length=512,
                                  actual_unpadded_input_tokens=tokens,expected_padded_tokens=padded,length_schedule_sha256=digest.hexdigest()))
if __name__=='__main__':main()

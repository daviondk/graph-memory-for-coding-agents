"""Package observed texts at a common actual length after all document choices are sealed."""
from base47 import *
from engine47 import enc,dec,model_check
import struct
def key(ts):return hexb(struct.pack('<'+'I'*len(ts),*ts))
def main():
    check();model_check()
    assert get(D/'retrieval-seal.json')['orders']==sha(D/'orders.json.gz')
    orders=get(D/'orders.json.gz');view=get(PRIVATE/'visible.json.gz')
    prev=signed(R46,'contexts.json.gz');baseprompts=signed(R46,'prompts.json.gz')
    end=enc('<|im_end|>\n<|im_start|>assistant\n',True);sep=enc('\nDocument 2:\n');first_sep=enc('\nDocument 1:\n')
    prompts={};text={};ctx={};short=0
    for q,r in orders.items():
        orig=prev[q];ix={i:(t,body) for i,t,body in view[q][1]}
        sel={'true':r['true'],'lex':r['lex'],**{'sham'+s:rec['second'] for s,rec in r['sham'].items()}}
        second={i:enc('\n'.join(ix[i]))[:192] for i in set(sel.values())}
        orig_n=orig['second_tokens'];new_n=min(orig_n,*map(len,second.values()))
        short+=new_n<orig_n
        true_orig=baseprompts[orig['prompt']['mention_expanded'][1]];lex_orig=baseprompts[orig['prompt']['expanded'][1]]
        cut=len(true_orig)-len(end)-orig_n;prefix=true_orig[:cut]
        f1end=cut-len(sep);f1begin=f1end-orig['first_tokens'];f1=tuple(prefix[f1begin:f1end])
        assert prefix[-len(sep):]==sep and prefix[f1begin-len(first_sep):f1begin]==first_sep
        assert true_orig==prefix+second[r['true']][:orig_n]+end and lex_orig==prefix+second[r['lex']][:orig_n]+end
        records={}
        for a,i in sel.items():
            part=second[i][:new_n];ts=prefix+part+end;k=key(ts)
            assert prompts.setdefault(k,ts)==ts;records[a]=[i,k,len(ts)]
            if k not in text:text[k]=[dec(f1),dec(tuple(part))]
        assert set(records)==set(ARMS) and len({v[2] for v in records.values()})==1
        ctx[q]=dict(cluster=orig['cluster'],seed=r['seed'],refs=records,n=new_n,original_n=orig_n,
            switch=(r['true']!=r['lex']),successful=(r['sham'][str(SEEDS[0])]['second']!=r['true']))
    put(D/'contexts.json.gz',ctx);put(D/'prompts.json.gz',prompts);put(P47/'delivered.json.gz',text)
    put(D/'input-seal.json',dict(retrieval=sha(D/'retrieval-seal.json'),contexts=sha(D/'contexts.json.gz'),
        prompts=sha(D/'prompts.json.gz'),texts=sha(P47/'delivered.json.gz'),builder=sha(D/'contexts47.py'),
        n=len(ctx),unique=len(prompts),shortened=short,logical=len(ctx)*len(ARMS)))
    print('frozen',len(ctx),len(prompts),'shortened',short,'new',len(set(prompts)-set(baseprompts)))
if __name__=='__main__':main()

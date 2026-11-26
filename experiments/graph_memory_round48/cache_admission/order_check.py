"""Post hoc sensitivity to iteration order of the supplied pool, using identical chronology, budgets and plans."""
from admission import D,Cache,capacity,read,write,sha
import hashlib,numpy as np
from collections import defaultdict
def main():
    w=read(D/'workload.json.gz');rows=w['rows'];pre=w['pre'];keys={int(k):bytes.fromhex(v) for k,v in read(D/'key-digests.json.gz').items()};cap=capacity(512);rec={}
    for mode in ['original','reverse','stable_hash','per_state_hash','cost_hot_last']:
        docs={}
        for q,z in rows.items():
            seq=z['order']
            if mode=='reverse':seq=seq[::-1]
            if mode=='stable_hash':seq=sorted(seq,key=lambda k:keys[k])
            if mode=='per_state_hash':seq=sorted(seq,key=lambda k:hashlib.sha256(q.encode()+keys[k]).digest())
            if mode=='cost_hot_last':seq=sorted(seq,key=lambda k:(z['docs'][str(k)],-int.from_bytes(keys[k],'big')))
            docs[q]={k:z['docs'][str(k)] for k in seq}
        rr={}
        for q,seq in pre.items():
            arm={}
            for a in ['hot_lru','batch_lru','tiny','proposed']:
                cache=Cache(a,cap,keys)
                for earlier in seq:cache.operate(docs[earlier])
                _,n=cache.operate(docs[q]);arm[a]=n
            rr[q]=arm
        rec[mode]=rr
    write('order-outcomes.json.gz',rec);summary={}
    repos=sorted({z['repo'] for z in rows.values()});groups=defaultdict(list)
    for q,z in rows.items():groups[z['repo']].append(q)
    den=np.asarray([sum(rows[q]['tokens'] for q in groups[k]) for k in repos]);n=len(repos);bs=np.random.default_rng(480532).multinomial(n,np.repeat(1/n,n),size=20000)
    for mode,rr in rec.items():
        totals={a:sum(v[a] for v in rr.values()) for a in ['proposed','hot_lru','batch_lru','tiny']};diff=np.asarray([sum(rr[q]['proposed']-rr[q]['hot_lru'] for q in groups[k]) for k in repos])
        summary[mode]=dict(tokens=totals,delta=diff.sum()/den.sum(),ci=np.quantile((bs@diff)/(bs@den),[.025,.975]).tolist())
    write('order-results.json',dict(program=sha(D/'order_check.py'),rows=sha(D/'order-outcomes.json.gz'),summary=summary,scope='Secondary descriptive order sensitivity after primary results.'))
    print(summary)
if __name__=='__main__':main()


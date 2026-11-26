"""Causal trajectory replay, exact-key versus aliases and finite-capacity LRU, no labels."""
from inventory import *
from collections import OrderedDict
import numpy as np
KEYS={'token':0,'text':2,'id':3,'path':4,'span':5}
def encode_history(qs,rows):return [v for q in qs for v in rows[q]['docs']]
def alias(old,docs,idx):
    cache={}
    for row in old:cache.setdefault(row[idx],row[0])
    correctly=wrong=right_t=wrong_t=0
    for row in docs:
        k,v,n=row[idx],row[0],row[1]
        if k in cache:
            if cache[k]==v:correctly+=1;right_t+=n
            else:wrong+=1;wrong_t+=n
        else:cache[k]=v
    return [correctly,wrong,right_t,wrong_t]
def finite(old,docs,cap):
    cache=OrderedDict()
    for row in old:
        tag=row[0];cache[tag]=None;cache.move_to_end(tag)
        if len(cache)>cap:cache.popitem(last=False)
    hits=toks=0
    for row in docs:
        tag=row[0]
        if tag in cache:hits+=1;toks+=row[1]
        cache[tag]=None;cache.move_to_end(tag)
        if len(cache)>cap:cache.popitem(last=False)
    return [hits,toks,len(cache)]
def query(q,previous,rows,full=True):
    old=encode_history(previous,rows);z=rows[q];docs=z['docs'];seen={v[0] for v in old};cur=set();inter=intra=inc=total=0;it=intt=inct=tot_t=0
    for v in docs:
        tag,n=v[:2];prior=tag in seen;local=tag in cur
        inter+=prior;intra+=local;inc+=prior and not local;total+=prior or local
        it+=n*prior;intt+=n*local;inct+=n*(prior and not local);tot_t+=n*(prior or local);cur.add(tag)
    assert inc+intra==total and inct+intt==tot_t
    d=dict(panel=z['panel'],repo=z['repo'],docs=len(docs),doc_tokens=sum(r[1] for r in docs),input_tokens=z['querylen']+sum(r[1] for r in docs),pre=len(previous),old_unique=len(seen),
           local_unique=len(cur),peak_keys=len(seen|cur),prior_docs=inter,prior_tokens=it,intra_docs=intra,intra_tokens=intt,extra_docs=inc,extra_tokens=inct,
           all_hits=total,all_tokens=tot_t,first=(not previous))
    if full:
        d['alias']={k:alias(old,docs,i) for k,i in KEYS.items()};d['lru']={str(cap):finite(old,docs,cap) for cap in (32,128)}
        assert d['alias']['token']==[total,0,tot_t,0] and d['alias']['text'][1]==0
    return d
def summarize(qs,counts,full):
    blocks=sorted({counts[q]['repo'] for q in qs});ix={s:j for j,s in enumerate(blocks)};k=len(blocks)
    fields=['docs','doc_tokens','input_tokens','prior_docs','prior_tokens','intra_docs','intra_tokens','extra_docs','extra_tokens','all_hits','all_tokens'];t=np.zeros((k,len(fields)))
    for q in qs:t[ix[counts[q]['repo']]]+=[counts[q][f] for f in fields]
    c={key:int(t[:,j].sum()) for j,key in enumerate(fields)};draw=np.random.default_rng(48052).multinomial(k,np.repeat(1/k,k),size=20000)
    def confidence(num,den):
        b=t[:,fields.index(den)];n=t[:,fields.index(num)];return dict(micro=float(n.sum()/b.sum()),macro=float(np.mean(n/b)),ci=np.quantile((draw@n)/(draw@b),[.025,.975]).tolist())
    v=dict(states=len(qs),repos=k,totals=c,first_states=sum(counts[q]['first'] for q in qs),states_with_prior_hits=sum(counts[q]['prior_docs']>0 for q in qs),primary=confidence('prior_tokens','input_tokens'),combined=confidence('all_tokens','input_tokens'),
           incremental=confidence('extra_tokens','input_tokens'),within=confidence('intra_tokens','input_tokens'),mean_peak_keys=float(np.mean([counts[q]['peak_keys'] for q in qs])),maximum_peak_keys=max(counts[q]['peak_keys'] for q in qs))
    if full:
        v['aliases']={k:np.asarray([counts[q]['alias'][k] for q in qs]).sum(0).tolist() for k in KEYS}
        v['bounded']={str(k):np.asarray([counts[q]['lru'][str(k)][:2] for q in qs]).sum(0).tolist() for k in (32,128)}
    return v
def main():
    sig=read(D/'input-seal.json');assert sha(D/'inventory.json.gz')==sig['inventory'] and sha(D/'predecessors.json')==sig['predecessors']
    rows=read(D/'inventory.json.gz');pre=read(D/'predecessors.json');groups=defaultdict(list)
    for q,z in rows.items():groups[z['group']].append(q)
    result={};table={}
    for key in ('causal','step','hash','reverse'):
        if key=='causal':mapping=pre
        else:
            mapping={}
            for members in groups.values():
                if key=='step':seq=sorted(members,key=lambda q:(rows[q]['step'],digest('r48-order'+q)))
                else:seq=sorted(members,key=lambda q:digest('r48-order'+q),reverse=key=='reverse')
                for i,q in enumerate(seq):mapping[q]=seq[:i]
        counts={q:query(q,h,rows,key=='causal') for q,h in mapping.items()};result[key]=counts
        table[key]={part:summarize([q for q,z in rows.items() if part=='both' or z['panel']==part],counts,key=='causal') for part in ('both','dev','outside')}
    shape=dict(states=len(rows),groups=len(groups),repeated_scopes=sum(len(v)>1 for v in groups.values()),strict_sources=sum(bool(v) for v in pre.values()),known_runs=sum(z['run_known'] for z in rows.values()),
               monotonic_steps=sum(z['monotonic'] for z in rows.values()),states_with_equal_prefix=sum(sum(tuple(rows[j]['hist'])==tuple(rows[q]['hist']) for j in groups[rows[q]['group']])>1 for q in rows))
    write('per-state.json.gz',result);write('reuse.json',dict(table=table,shape=shape,source=sha(D/'input-seal.json'),output=sha(D/'per-state.json.gz'),program=sha(Path(__file__))))
    v=table['causal']['both'];print('Primary',v['primary'],'total',v['totals'],'shape',shape)
if __name__=='__main__':main()


import base64,statistics
from collections import Counter,defaultdict
import numpy as np
from dictionary import encnum,getnum,envelope
from grade12 import tally
from util12 import D,load,dump,sha
from store12 import initial,H
from write import pages,SEEDS
from gcs import lookup
def encode_patch(prev,new):
    if prev==new:return b'',[]
    length=len(new);ranges=[]
    for i,o in enumerate(new):
        if i<len(prev) and prev[i]==o:continue
        if ranges and i-ranges[-1][1]<=2:ranges[-1][1]=i+1
        else:ranges.append([i,i+1])
    seq=bytearray(b'\x01'+encnum(length)+encnum(len(ranges)));offset=0
    for a,b in ranges:
        seq+=encnum(a-offset)+encnum(b-a)+new[a:b];offset=b
    full=b'\x00'+new
    return (full,[(0,length)]) if len(full)<=len(seq) else (bytes(seq),ranges)
def apply_patch(prev,wire):
    if not wire:return prev
    if wire[0]==0:return wire[1:]
    n,pos=getnum(wire,1);m,pos=getnum(wire,pos)
    ret=bytearray(prev[:n]);ret+=bytes(n-len(ret));offset=0
    for _ in range(m):
        gap,pos=getnum(wire,pos);ln,pos=getnum(wire,pos);a=offset+gap
        ret[a:a+ln]=wire[pos:pos+ln];pos+=ln;offset=a+ln
    assert pos==len(wire);return bytes(ret)
def main():
    for p,h in load(D/'gcs_seal.json').items():assert sha(D/p)==h
    data=defaultdict(Counter);patchrecords=[];gcsrows=[]
    for p in sorted((D/'events').glob('*.gz')):
        e=load(p);n=e['n'];t=e['task'];qs=load(D/'probes'/p.name);truth={};hist={};closed=[];keys=qs['keys']
        for ev in e['events']:
            bit=1<<ev['i'];truth={k:v&~bit for k,v in truth.items() if v&~bit}
            for w in ev['words']:truth[w]=truth.get(w,0)|bit;hist[w]=hist.get(w,0)|bit
            closed.append((dict(truth),dict(hist)))
        prev={}
        def rec(step,phase,b,s,gate,arm,raw,first):
            idx=(b,s,gate,arm);o=prev.get(idx,first);wire,rg=encode_patch(o,raw)
            assert apply_patch(o,wire)==raw
            # Size/directory metadata needed when changing logical length accounted in wire bytes.
            pp64=pages(rg,64);pp4k=pages(rg,4096)
            data[t,phase,b,s,gate,arm].update(patch=len(wire),p64=pp64,p4k=pp4k,events=1)
            patchrecords.append([t,step,phase,b,s,gate,arm,len(wire),pp64,pp4k]);prev[idx]=raw
        for step,phase,b,s,gate,arm,enc,rg,reads,st in load(D/'states'/p.name)['rows']:
            rec(step,phase,b,s,gate,arm,base64.b64decode(enc),initial(arm,n,b,s))
        for step,phase,b,gate,enc,reads,st in load(D/'exact_states'/p.name):
            arm='mutable_exact' if b else 'uncapped_exact';raw=base64.b64decode(enc)
            for s in SEEDS:rec(step,phase,b,s,gate,arm,raw,envelope({},n,0))
        for step,phase,b,s,gate,enc,rg,replay in load(D/'gcs_states'/p.name):
            raw=base64.b64decode(enc);rec(step,phase,b,s,gate,'gcs',raw,bytes([90,n,s,0,0,0,0,0])+bytes(n*b-H))
            lookup_fn=lookup(raw);vals={key:lookup_fn(key) for key in keys}
            score=tally(vals,*closed[step],set(qs['changed_definitions']),set(qs['guaranteed_absent']),n)
            score.update(emit=sum(v-u for u,v in rg),replay=replay)
            data[t,phase,b,s,gate,'gcs'].update(score)
            gcsrows.append([t,step,phase,b,s,gate,base64.b64encode(bytes(vals[k] for k in keys)).decode(),dict(score)])
    storage={};mod={}
    for t,phase,b,s,g,a in data:
        full='/'.join(map(str,[phase,b,g,a]));m=mod.setdefault(full,{}).setdefault(t,Counter())
        m.update(data[t,phase,b,s,g,a])
    for k,v in mod.items():
        acc=Counter()
        for z in v.values():acc.update(z)
        storage[k]=dict(wire=acc['patch']/acc['events'],page64=acc['p64']/acc['events'],page4k=acc['p4k']/acc['events'])
        if k.endswith('/gcs'):
            storage[k].update(fp=acc['fp']/acc['tn_all'],semantic_fp=acc['chg_fp']/acc['chg_tn'],stale=acc['stale']/max(1,acc['stale_possible']),missed=acc['missed'],emit=acc['emit']/acc['events'],replay=acc['replay']/acc['events'])
    rng=np.random.default_rng(12041);ids=sorted(next(iter(mod.values())));bootstrap=rng.integers(0,len(ids),(10000,len(ids)));effects={}
    main=load(D/'results.json')['cells']
    for b in [64,256]:
        a=f'1/{b}/0/gcs';bloom=f'1/{b}/0/column_bloom'
        x=np.array([mod[a][i]['fp']/mod[a][i]['tn_all']-main[bloom]['modules'][i].get('fp',0)/main[bloom]['modules'][i]['tn_all'] for i in ids]);sim=x[bootstrap].mean(1)
        effects[b]=dict(delta=x.mean(),lo=float(np.quantile(sim,.025)),hi=float(np.quantile(sim,.975)),per_module=x.tolist(),ids=ids)
    dump(D/'patch_rows.json.gz',patchrecords);dump(D/'gcs_reads.json.gz',gcsrows)
    dump(D/'patch_results.json',dict(metrics=storage,modules=mod,gcs_minus_bloom_macro_fp=effects))
if __name__=='__main__':main()
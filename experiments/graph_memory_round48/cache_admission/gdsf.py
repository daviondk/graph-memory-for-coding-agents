from admission import D,BASE,BUDGETS,capacity,Cache,read,write,sha
from collections import defaultdict
import numpy as np
MODES=('source','hits_first','batch')
class GD:
    def __init__(self,mode,limit,h):
        self.mode=mode;self.limit=limit;self.h=h;self.res={};self.clock=0
    def update(self,docs):
        old=self.res;hits=[x for x in docs if x in old];miss=[x for x in docs if x not in old];cn=len(hits);saving=sum(docs[x] for x in hits)
        if self.mode=='batch':
            pool=old.copy()
            for x,cost in docs.items():
                f=old.get(x,(0,0))[1]+1;pool[x]=(self.clock+f*cost,f)
            chosen=sorted(pool,key=lambda x:(-pool[x][0],self.h[x]))[:self.limit]
            dropped=old.keys()-set(chosen)
            if dropped:self.clock=max(self.clock,max(pool[x][0] for x in dropped))
            self.res={x:pool[x] for x in chosen}
        else:
            keys=list(docs) if self.mode=='source' else hits+miss
            for x in keys:
                prev=old.get(x,(0,0))[1];f=prev+1;old[x]=(self.clock+f*docs[x],f)
                if len(old)>self.limit:
                    victim=min(old,key=lambda k:(old[k][0],-self.h[k]))
                    value,_=old.pop(victim)
                    if victim!=x:self.clock=value
        return cn,saving
def aggregate(qs,rows,res,base,cap):
    group=defaultdict(list)
    for q in qs:group[rows[q]['repo']].append(q)
    gr=sorted(group);n=len(gr);den=np.asarray([sum(rows[q]['tokens'] for q in group[k]) for k in gr]);boot=np.random.default_rng(480532).multinomial(n,np.repeat(1/n,n),size=20000)
    p=np.asarray([sum(base[q]['caps'][str(cap)]['proposed']['saved'] for q in group[k]) for k in gr]);common=boot@den
    out={}
    for mode in MODES:
        obs=[res[q][str(cap)][mode] for q in qs];sav=np.asarray([sum(res[q][str(cap)][mode]['saved'] for q in group[k]) for k in gr]);d=p-sav
        dd=[base[q]['caps'][str(cap)]['proposed']['saved']-res[q][str(cap)][mode]['saved'] for q in qs]
        out[mode]=dict(tokens=int(sav.sum()),hits=sum(z['hits'] for z in obs),fraction=sav.sum()/sum(den),delta=d.sum()/sum(den),macro=float(np.mean(d/den)),
                  ci=np.quantile((boot@d)/common,[.025,.975]).tolist(),wins=sum(v>0 for v in dd),loss=sum(v<0 for v in dd))
    return out
def main():
    assert sha(D/'GDSF_PROTOCOL_RU.md')=='52acbfd6847d07a6ff01a73e9ec18d63c4aad3150f06fe66b371c6046c36d85d'
    wk=read(D/'workload.json.gz');rows=wk['rows'];pre=wk['pre'];base=read(D/'outcomes.json.gz');hashes={int(k):bytes.fromhex(v) for k,v in read(D/'key-digests.json.gz').items()};h={k:int.from_bytes(v,'big') for k,v in hashes.items()}
    docs={q:{k:z['docs'][str(k)] for k in z['order']} for q,z in rows.items()};out={}
    for q,prior in pre.items():
        caps={}
        for kb in BUDGETS:
            v={}
            for m in MODES:
                gd=GD(m,capacity(kb),h)
                for old in prior:gd.update(docs[old])
                cc=list(gd.res);cn,t=gd.update(docs[q]);v[m]=dict(hits=cn,saved=t,prior=cc)
            caps[str(kb)]=v
        out[q]=caps
    write('gdsf-outcomes.json.gz',out);panels={}
    for budget in BUDGETS:
        panels[str(budget)]={p:aggregate([q for q,z in rows.items() if p=='both' or z['panel']==p],rows,out,base,budget) for p in ('both','dev','outside')}
    # These pairs restart cold, even if additional real predecessors were available in the primary sequence.
    gp=read(BASE/'gpu-results.json.gz');src=read(BASE/'inventory.json.gz');rep=[]
    for v in gp:
        pair=v['pair'];raw=sum(z['tokens'] for z in v['runs']['fresh'])
        unique_inputs=raw
        for q in pair:
            # row.tokens includes the query and all docs; the saved difference directly measures local dedup.
            z=src[q];unique_inputs-=sum(d[1] for d in z['docs'])-sum(docs[q].values())
        arm={}
        for m in ['proposed','hot_lru','cost',*MODES]:
            pol=GD(m,capacity(512),h) if m in MODES else Cache(m,capacity(512),hashes);ss=0
            for q in pair:
                cnt,t=(pol.update(docs[q]) if m in MODES else pol.operate(docs[q]));ss+=t
            arm[m]=dict(input_tokens=unique_inputs-ss,inter_saved=ss)
        rep.append(dict(pair=pair,raw=raw,intra_dedup_input=unique_inputs,arms=arm,actual_unlimited_tokens=sum(z['tokens'] for z in v['runs']['cached'])))
    write('gdsf-results.json',dict(protocol=sha(D/'GDSF_PROTOCOL_RU.md'),program=sha(D/'gdsf.py'),primary=sha(D/'results.json'),rows=sha(D/'gdsf-outcomes.json.gz'),
          panels=panels,gpu_pairs=rep,scope='GPU pairs: token replay only; numbers for fresh and unlimited are from a real run.'))
    print(panels['512']['both'])
if __name__=='__main__':main()


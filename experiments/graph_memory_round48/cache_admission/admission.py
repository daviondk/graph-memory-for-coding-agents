"""Bounded, batch-aware vector cache replay. All measurements probe a frozen initial snapshot."""
from pathlib import Path
from collections import OrderedDict,defaultdict
import hashlib,gzip,json,struct,sys,time
import numpy as np
D=Path(__file__).resolve().parent;BASE=D.parent/'embedding_reuse'
sys.path.insert(0,str(BASE))
from inventory import read,sha,key,TOK,canonical
PROTO='edb69b47f8d37cc34e856536560e5244b29852977509a62ad371eff3f82c7fcd'
METHODS=('proposed','hot_lru','batch_lru','slru','tiny','hash','cost','freq','oracle')
BUDGETS=(128,512,2048);HEAD=256;SKETCH=1024;PAYLOAD=16384;SLOT=struct.Struct('<32sIHHfII12x')
assert SLOT.size==64
def write(name,value):
    b=canonical(value)+b'\n';(D/name).write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if name.endswith('.gz') else b)
def capacity(kb):return (1024*kb-HEAD-SKETCH)//(PAYLOAD+SLOT.size)
def reduce(state):
    return dict((z[0],z[1]) for z in state['docs'])
class Cache:
    def __init__(self,name,cap,keys):
        self.method=name;self.cap=cap;self.keys=keys;self.res=OrderedDict();self.pro=OrderedDict();self.sk=bytearray(SKETCH);self.tick=0
    def freq(self,k):
        v=self.keys[k];return min(self.sk[256*i+v[i]] for i in range(4))
    def count(self,k):
        if self.tick and self.tick%1024==0:self.sk=bytearray(x//2 for x in self.sk)
        self.tick+=1
        for i,ix in enumerate(self.keys[k][:4]):
            j=256*i+ix
            if self.sk[j]<255:self.sk[j]+=1
    def entries(self):return dict(self.res)|dict(self.pro)
    def operate(self,docs):
        before=self.entries();hits=[k for k in docs if k in before];miss=[k for k in docs if k not in before];m=self.method
        if m in ('hot_lru','batch_lru'):
            order=miss+hits if m=='hot_lru' else list(docs)
            for k in order:
                self.res[k]=docs[k];self.res.move_to_end(k)
                if len(self.res)>self.cap:self.res.popitem(last=False)
        elif m=='slru':
            # Snapshot hits are protected before admission of misses. res is probation, pro is protected.
            maxpro=max(1,min(self.cap-1,int(.8*self.cap)))
            for k in hits:
                self.res.pop(k,None);self.pro[k]=docs[k];self.pro.move_to_end(k)
                if len(self.pro)>maxpro:
                    old,n=self.pro.popitem(last=False);self.res[old]=n
            for k in miss:
                self.res[k]=docs[k]
                while len(self.res)+len(self.pro)>self.cap:self.res.popitem(last=False)
        elif m=='tiny':
            for k in docs:self.count(k)
            for k in hits:self.res.move_to_end(k)
            for k in miss:
                if len(self.res)==self.cap:
                    victim=next(iter(self.res))
                    if self.freq(k)<=self.freq(victim):continue
                    del self.res[victim]
                self.res[k]=docs[k]
        else:
            if m in ('proposed','freq'):
                for k in docs:self.count(k)
            pool=before|docs
            def criterion(k):
                a=(pool[k] if m in ('proposed','cost') else 1)*(1+self.freq(k) if m in ('proposed','freq') else 1)
                return (-a,self.keys[k])
            self.res=OrderedDict((k,pool[k]) for k in sorted(pool,key=criterion)[:self.cap])
        return len(hits),sum(docs[k] for k in hits)
    def pack(self):
        # A portable packed metadata layout, separate from 4096-float payloads. Record order serializes LRU order.
        head=struct.pack('<III',self.cap,self.tick,len(self.res))+bytes(HEAD-12)
        rr=list(self.res.items())+list(self.pro.items())
        records=b''.join(SLOT.pack(self.keys[k],i,1 if k in self.pro else 0,0,float(n),0,0) for i,(k,n) in enumerate(rr))
        meta=head+bytes(self.sk)+records
        return len(meta),len(rr),hashlib.sha256(meta).hexdigest()
def aggregate(qs,outs,budget):
    names=sorted({outs[q]['repo'] for q in qs});loc={z:i for i,z in enumerate(names)};n=len(names)
    total=np.zeros(n);mat=np.zeros((n,len(METHODS)));docs=np.zeros_like(mat);win=np.zeros(len(METHODS),int);loss=win.copy();obs=[]
    for q in qs:
        z=outs[q];j=loc[z['repo']];total[j]+=z['tokens'];v=[z['caps'][str(budget)][k] for k in METHODS];vals=np.array([x['saved'] for x in v]);mat[j]+=vals;docs[j]+=[x['hits'] for x in v];obs.append(vals)
    obs=np.array(obs);wt=np.random.default_rng(480532).multinomial(n,np.repeat(1/n,n),size=20000);den=wt@total;a={};c={}
    for i,m in enumerate(METHODS):
        a[m]=dict(tokens=int(mat[:,i].sum()),hits=int(docs[:,i].sum()),fraction=mat[:,i].sum()/total.sum(),macro=float(np.mean(mat[:,i]/total)),ci=np.quantile((wt@mat[:,i])/den,[.025,.975]).tolist())
    for name in ('hot_lru','batch_lru','slru','tiny','hash','freq','cost','oracle'):
        i,j=METHODS.index('proposed'),METHODS.index(name);dr=mat[:,i]-mat[:,j];ds=obs[:,i]-obs[:,j]
        c['proposed minus '+name]=dict(delta=dr.sum()/total.sum(),ci=np.quantile((wt@dr)/den,[.025,.975]).tolist(),macro=float(np.mean(dr/total)),wins=int((ds>0).sum()),loss=int((ds<0).sum()))
    return dict(states=len(qs),repos=n,input_tokens=int(total.sum()),methods=a,contrasts=c)
def main():
    assert sha(D/'PROTOCOL_RU.md')==PROTO and sha(BASE/'manifest.json')=='47680b8433bd3392d874734cc2ffbac1bb9f15062f84b70e293669390671bbc6'
    src=read(BASE/'input-seal.json');rows=read(BASE/'inventory.json.gz');pre=read(BASE/'predecessors.json');tok=read(TOK);assert sha(TOK)==src['source']
    keys={};text={}
    for q,z in rows.items():
        for a,i in zip(z['docs'],tok['states'][q]['doc']):
            if i not in text:text[i]=bytes.fromhex(key(src['namespace'],tok['tokens'][i][1]))
            assert a[0] not in keys or keys[a[0]]==text[i];keys[a[0]]=text[i]
    assert len(keys)==len(set(keys.values()))==src['keys']
    write('key-digests.json.gz',{k:v.hex() for k,v in keys.items()});write('workload.json.gz',dict(rows={q:dict(docs=reduce(z),order=list(reduce(z)),repo=z['repo'],panel=z['panel'],tokens=z['querylen']+sum(t[1] for t in z['docs'])) for q,z in rows.items()},pre=pre))
    packets={q:reduce(z) for q,z in rows.items()};out={};clock=time.perf_counter()
    for q,z in rows.items():
        unit=packets[q];old=pre[q];before=set().union(*(set(packets[k]) for k in old));v={}
        for mem in BUDGETS:
            cap=capacity(mem);a={}
            for method in METHODS:
                if method=='oracle':
                    best=sorted(before.intersection(unit),key=lambda k:(-unit[k],keys[k]))[:cap];a[method]=dict(hits=len(best),saved=sum(unit[k] for k in best));continue
                reader=Cache(method,cap,keys)
                for h in old:reader.operate(packets[h])
                # All pre-state residents are saved for a label-free independent check of hits and capacity.
                cached=list(reader.entries());nb,n0,fpr=reader.pack();assert n0==len(cached) and nb+n0*PAYLOAD<=mem*1024 and set(cached)<=before
                hit,t=reader.operate(unit);nb1,n1,h1=reader.pack();assert nb1+n1*PAYLOAD<=mem*1024
                a[method]=dict(hits=hit,saved=t,cache=cached,packed_metadata=nb,packed_keys=n0,metadata_sha=fpr)
            v[str(mem)]=a
        out[q]=dict(repo=z['repo'],panel=z['panel'],tokens=z['querylen']+sum(k[1] for k in z['docs']),caps=v)
    write('outcomes.json.gz',out);panels={}
    for size in BUDGETS:
        panels[str(size)]={p:aggregate([q for q,z in out.items() if p=='both' or z['panel']==p],out,size) for p in ['both','dev','outside']}
    write('results.json',dict(scope=sha(BASE/'manifest.json'),protocol=PROTO,outcomes=sha(D/'outcomes.json.gz'),workload=sha(D/'workload.json.gz'),keymap=sha(D/'key-digests.json.gz'),
         program=sha(Path(__file__)),panels=panels,budgets={str(m):dict(bytes=m*1024,slots=capacity(m),lru_no_sketch=(m*1024-HEAD)//(PAYLOAD+64)) for m in BUDGETS},
         header=HEAD,sketch=SKETCH,meta_per_slot=SLOT.size,payload_per_slot=PAYLOAD,replay_seconds=time.perf_counter()-clock))
    print(panels['512']['both']['contrasts']['proposed minus hot_lru'])
if __name__=='__main__':main()


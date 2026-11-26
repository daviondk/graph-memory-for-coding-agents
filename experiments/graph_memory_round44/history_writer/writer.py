"""Path-global writer with charged addressing, access metadata, UTF-8 bodies and actual serialization."""
from common import Counter,HEADER,REF,LENGTH,hashlib

class Writer:
    def __init__(self,mode,cap):
        self.mode=mode;self.cap=cap;self.rows={};self.max_size=8;self.evicted=0;self.conflicts=0

    def clear(self):self.rows.clear()

    def remove_path(self,path):
        for k in [k for k in self.rows if k[0]==path]:self.rows.pop(k)

    def read(self,path,at,visible):
        if self.mode=="latest":self.remove_path(path)
        for line,dg,size,eligible in visible:
            key=(path,line);prior=self.rows.get(key)
            if prior is not None and prior[0]!=dg:
                self.rows.pop(key);prior=None;self.conflicts+=1
            if eligible:
                self.rows[key]=(dg,size,prior[2] if prior else at,at,min(65535,prior[4]+1) if prior else 1)
        amounts={v[0]:v[1] for v in self.rows.values()}
        count=Counter(v[0] for v in self.rows.values())
        size=HEADER.size+REF.size*len(self.rows)+sum(LENGTH.size+n for n in amounts.values())
        if self.cap is not None and size>self.cap:
            representative={}
            if self.mode=="distinct":
                for key,v in self.rows.items():
                    old=representative.get(v[0])
                    if old is None or (v[3],v[2],key)>(self.rows[old][3],self.rows[old][2],old):representative[v[0]]=key
            def eviction(key):
                dg,n,first,last,freq=self.rows[key]
                if self.mode=="first":return (-first,-last,key)
                if self.mode=="lfu":return (freq,last,first,key)
                if self.mode=="distinct":return (int(representative[dg]==key),last,first,key)
                return (last,first,key)
            for k in sorted(self.rows,key=eviction):
                dg,n,*_=self.rows.pop(k);self.evicted+=1;count[dg]-=1;size-=REF.size
                if not count[dg]:size-=LENGTH.size+n
                if size<=self.cap:break
        assert self.cap is None or size<=self.cap
        self.max_size=max(self.max_size,size)

    def wire(self,bodies):
        keys=sorted(self.rows);ids=sorted({self.rows[k][0] for k in keys});index={d:i for i,d in enumerate(ids)}
        out=bytearray(HEADER.pack(len(keys),len(ids)))
        for path,n in keys:
            dg,length,first,last,freq=self.rows[path,n]
            out+=REF.pack(bytes.fromhex(path),n,first,last,freq,index[dg])
        size=0
        for d in ids:
            body=bodies[d];out+=LENGTH.pack(len(body))+body;size+=len(body)
        assert len(out)==HEADER.size+REF.size*len(keys)+LENGTH.size*len(ids)+size
        assert self.cap is None or len(out)<=self.cap
        return [len(out),len(keys),len(ids),size,hashlib.sha256(out).hexdigest()]


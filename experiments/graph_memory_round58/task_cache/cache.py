"""Line-address memory, optional exact content interning, and byte-bounded selectors."""
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import struct

ARMS=("global","file","segmented","global_intern","file_intern","segmented_intern")

@dataclass(frozen=True,slots=True)
class Row:
    uid:object
    size:int
    tick:int
    protected:bool=False

@lru_cache(maxsize=5000)
def name_cost(path):
    return 4+len(path.encode("utf8"))

class Budget:
    def __init__(self,capacity,row_bytes,interned,payload_only=False):
        self.cap=capacity;self.row=row_bytes;self.interned=interned;self.plain=payload_only
        self.used=0 if payload_only else 8
        self.files=set();self.uids=set();self.pointers=0;self.body=0
    def take(self,key,cell):
        path,_=key
        duplicate=self.interned and cell.uid in self.uids
        extra_body=0 if duplicate else cell.size
        added=extra_body
        if not self.plain:added+=self.row+(0 if path in self.files else name_cost(path))
        if self.used+added>self.cap:return False
        self.used+=added;self.body+=extra_body
        self.files.add(path);self.uids.add(cell.uid);self.pointers+=duplicate
        return True

class Cache:
    def __init__(self,arm,capacity,row_bytes=12,payload_only=False):
        self.kind=arm.split("_")[0];self.intern=arm.endswith("_intern");self.cap=capacity
        self.row_bytes=row_bytes;self.payload_only=payload_only
        self.tick=0;self.cells={};self.files={}
    def clear(self):
        self.cells.clear();self.files.clear();self.tick=0
    def serve(self,path,lines):
        n=hits=conflict=0
        for line,uid,size in lines:
            cell=self.cells.get((path,line))
            if cell is not None:
                if uid==cell.uid:
                    assert size==cell.size
                    hits+=size;n+=1
                else:conflict+=1
        return [hits,int(n==len(lines)),conflict]
    def update(self,path,lines):
        for line,uid,size in lines:
            key=(path,line);old=self.cells.get(key)
            protect=self.kind=="segmented" and old is not None and old.uid==uid
            self.tick+=1
            self.cells[key]=Row(uid,size,self.tick,protect)
        self.files[path]=self.tick
        by_age=sorted(self.cells,key=lambda k:self.cells[k].tick,reverse=True)
        if self.kind=="file":
            order=sorted(by_age,key=lambda k:self.files[k[0]],reverse=True)
        elif self.kind=="segmented":
            half=Budget(self.cap//2,self.row_bytes,self.intern,self.payload_only)
            hot=set()
            for k in by_age:
                v=self.cells[k]
                if v.protected:
                    if half.take(k,v):hot.add(k)
                    else:self.cells[k]=Row(v.uid,v.size,v.tick,False)
            order=[k for k in by_age if k in hot]+[k for k in by_age if k not in hot]
        else:order=by_age
        budget=Budget(self.cap,self.row_bytes,self.intern,self.payload_only)
        survivors={k:self.cells[k] for k in order if budget.take(k,self.cells[k])}
        skipped=len(self.cells)-len(survivors)
        self.cells=survivors;self.files={p:self.files[p] for p in budget.files}
        return [budget.used,len(self.cells),budget.pointers,skipped,budget.body]
    def ordered(self):
        return (sorted(self.files,key=self.files.get),
                sorted(self.cells,key=lambda k:self.cells[k].tick))

def encode(cache,texts):
    assert cache.row_bytes==12 and not cache.payload_only
    files,keys=cache.ordered();indexes={p:i for i,p in enumerate(files)}
    first={};raw=bytearray(struct.pack("<II",len(files),len(keys)))
    for path in files:
        value=path.encode("utf8")
        raw.extend(struct.pack("<I",len(value)));raw.extend(value)
    for i,key in enumerate(keys):
        path,line=key;c=cache.cells[key];ref=cache.intern and c.uid in first
        payload=first[c.uid] if ref else c.size
        tag=(payload<<2)|int(ref)|(int(c.protected)<<1)
        raw.extend(struct.pack("<III",indexes[path],line,tag))
        if not ref:
            content=texts[c.uid];assert len(content)==c.size
            raw.extend(content);first[c.uid]=i
    return bytes(raw)

def decode(raw):
    nf,n=struct.unpack_from("<II",raw);pos=8;files=[];rows=[]
    for _ in range(nf):
        length,=struct.unpack_from("<I",raw,pos);pos+=4
        files.append(raw[pos:pos+length].decode("utf8"));pos+=length
    for i in range(n):
        f,line,tag=struct.unpack_from("<III",raw,pos);pos+=12
        if tag&1:
            assert tag>>2<i
            text=rows[tag>>2][2]
        else:
            length=tag>>2;text=raw[pos:pos+length];pos+=length
        rows.append((files[f],line,text,bool(tag&2)))
    assert pos==len(raw) and len(set(files))==len(files)
    return files,rows

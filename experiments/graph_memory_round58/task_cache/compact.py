"""Compact file-group checkpoints. The same incremental costs guide admission and encoding."""
from collections import Counter
from hashlib import sha256
import struct
from cache import Cache,Row
from replay import HERE,PAST,load,save

def leb(n):
    out=bytearray()
    while n>=128:out.append(128+(n&127));n>>=7
    out.append(n);return bytes(out)

def leb_len(n):return max(1,(n.bit_length()+6)//7)
def zig(n):return 2*n if n>=0 else -2*n-1
def unzig(n):return n//2 if n%2==0 else -(n//2)-1

class FileCache(Cache):
    def __init__(self,cap,scheme,fixed=False):
        super().__init__("file",cap)
        self.scheme=scheme;self.fixed=fixed
    def update(self,path,lines):
        for line,uid,size in lines:
            self.tick+=1
            self.cells[path,line]=Row(uid,size,self.tick,False)
        self.files[path]=self.tick
        order=sorted(self.cells,key=lambda key:(self.files[key[0]],self.cells[key].tick),reverse=True)
        files={};last={};saved={};used=8 if self.fixed else 2;count=0;refs=0
        for key in order:
            p,n=key;cell=self.cells[key];u=cell.uid if self.scheme=="all" else (p,cell.uid)
            new_file=p not in files
            use_ref=self.scheme!="none" and u in last
            path_size=len(p.encode("utf8"))
            if self.fixed:
                add=12+(0 if use_ref else cell.size)+(4+path_size if new_file else 0)
            else:
                literal=leb_len(cell.size*2)+cell.size
                pointer=leb_len(2*(count-last[u]-1)+1) if use_ref else literal
                use_ref=use_ref and pointer<literal
                add=leb_len(zig(n-files.get(p,0)))+(pointer if use_ref else literal)
                if new_file:add+=leb_len(path_size)+path_size+2
            if used+add>self.cap:continue
            used+=add;count+=1;refs+=use_ref
            last[u]=count-1;files[p]=n;saved[key]=cell
        self.cells=saved;self.files={p:self.files[p] for p in files}
        return used,refs

def serialize(c,strings):
    assert not c.fixed
    files=sorted(c.files,key=c.files.get,reverse=True)
    raw=bytearray(struct.pack("<H",len(files)));nrows=0;last={}
    for p in files:
        keys=sorted((k for k in c.cells if k[0]==p),key=lambda k:c.cells[k].tick,reverse=True)
        path=p.encode("utf8")
        raw+=leb(len(path))+path+struct.pack("<H",len(keys));line=0
        for k in keys:
            cell=c.cells[k]
            content=strings[cell.uid];assert len(content)==cell.size
            raw+=leb(zig(k[1]-line));line=k[1]
            u=cell.uid if c.scheme=="all" else (p,cell.uid)
            literal=leb(len(content)*2)+content
            ref=leb(2*(nrows-last[u]-1)+1) if c.scheme!="none" and u in last else literal
            raw+=ref if len(ref)<len(literal) else literal
            last[u]=nrows;nrows+=1
    return bytes(raw)

def unpack(buf):
    i=0
    def read(n):
        nonlocal i
        out=buf[i:i+n];i+=n
        assert len(out)==n
        return out
    def var():
        n=off=0
        while True:
            b=read(1)[0];n|=(b&127)<<off
            if b<128:return n
            off+=7
    files=[];rows=[]
    for _ in range(int.from_bytes(read(2),"little")):
        p=read(var()).decode();files.append(p);line=0
        for _ in range(int.from_bytes(read(2),"little")):
            line+=unzig(var());tag=var()
            text=rows[len(rows)-1-(tag>>1)][2] if tag&1 else read(tag>>1)
            rows.append((p,line,text))
    assert i==len(buf)
    return files,rows

def main():
    output=[];counts=Counter()
    for trace in load(PAST/"prefixes.json.gz"):
        cache={str(cap)+"_"+s:FileCache(cap,s) for cap in (4096,16384,65536) for s in ("all","file","none")}
        cache.update({"fixed_"+s:FileCache(16384,s,True) for s in ("all","file","none")})
        for t,e in enumerate(trace["events"]):
            if e[0]=="barrier":
                for c in cache.values():c.clear()
            if len(e)!=3:continue
            _,p,lines=e
            scores={name:c.serve(p,lines) for name,c in cache.items()}
            states={name:c.update(p,lines) for name,c in cache.items()}
            assert all(states[k][0]<=c.cap for k,c in cache.items())
            output.append(dict(issue=trace["issue"],actor=trace["actor"],repo=trace["repo"],at=t,bytes=sum(l[2] for l in lines),
                               score=scores,occupancy=states))
    old=load(HERE/"windows.json.gz")
    for x,y in zip(old,output,strict=True):
        assert (x["issue"],x["actor"],x["at"])==(y["issue"],y["actor"],y["at"])
        for k,m in (("none","file"),("all","file_intern")):
            assert x["score"]["16384_12_"+m]==y["score"]["fixed_"+k]
            assert x["state"]["16384_12_"+m][0]==y["occupancy"]["fixed_"+k][0]
    save(HERE/"compact-windows.json.gz",output,False)
    keys=list(output[0]["score"])
    summary={k:dict(hit_bytes=sum(r["score"][k][0] for r in output),full=sum(r["score"][k][1] for r in output),
                    conflict=sum(r["score"][k][2] for r in output),peak=max(r["occupancy"][k][0] for r in output))
                    for k in keys}
    save(HERE/"compact-results.json",summary,False)
    print([(k,v["hit_bytes"],v["full"]) for k,v in summary.items()])
if __name__=="__main__":main()

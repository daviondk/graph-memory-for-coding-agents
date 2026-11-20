"""Minimal BSON decoder for the types in the official archival MongoDB export."""
import struct
import datetime

def read_doc(buf,i=0,meta=False):
    end=i+struct.unpack_from('<i',buf,i)[0]-1
    i+=4
    out={}
    while i<end:
        t=buf[i]
        i+=1
        n=buf.index(0,i)
        k=buf[i:n].decode()
        i=n+1
        if t in (3,4):
            v,i=read_doc(buf,i,meta)
            if t==4:v=list(v.values())
        elif t in (2,13,14):
            n=struct.unpack_from('<i',buf,i)[0];i+=4
            v=buf[i:i+n-1].decode('utf8','replace');i+=n
        elif t==7:
            v=buf[i:i+12].hex();i+=12
        elif t==8:
            v=bool(buf[i]);i+=1
        elif t in (9,17,18):
            v=struct.unpack_from('<q',buf,i)[0];i+=8
        elif t==1:
            v=struct.unpack_from('<d',buf,i)[0];i+=8
        elif t==16:
            v=struct.unpack_from('<i',buf,i)[0];i+=4
        elif t==5:
            n=struct.unpack_from('<i',buf,i)[0];i+=5
            v=buf[i:i+n];i+=n
        elif t==10:v=None
        else:raise RuntimeError((t,k))
        out[k]=v
    assert i==end and buf[end]==0
    return out,end+1

def docs(fp):
    while True:
        head=fp.read(4)
        if not head:break
        n=struct.unpack('<i',head)[0];assert 5<=n<=17000000,n
        buf=head+fp.read(n-4); assert len(buf)==n
        yield read_doc(buf)[0]

"""Source-bound checkpoint frames for copied bodies and referential selections."""
from itertools import accumulate
from pathlib import Path
import sys
import zlib

R58=Path(__file__).resolve().parents[2]/"graph_memory_round58"
sys.path.insert(0,str(R58/"restart"))
from checkpoint import BASE, CRC, HEADER, take_int, unpack, varints

COPY=0
ABSOLUTE=1
DELTA=2
EXCLUDED=3
BITMAP=4


def diffs(ids):
    previous=-1
    out=[]
    for j in ids:
        out.append(j-previous-1)
        previous=j
    return varints(out)


def encode(chosen, fence, sha, kind):
    ids=sorted(chosen)
    if kind in ("copy","compressed"):
        raw=bytearray()
        for j in ids:
            body=varints(chosen[j])
            raw.extend(varints((j,len(body))))
            raw.extend(body)
        layouts={COPY:bytes(raw)}
    else:
        mask=bytearray((fence+7)//8)
        for j in ids:
            mask[j//8]|=1<<(j%8)
        layouts={ABSOLUTE:varints(ids),DELTA:diffs(ids),
                 EXCLUDED:diffs(j for j in range(fence) if j not in chosen),BITMAP:bytes(mask)}
    if kind!="copy":
        layouts.update({k+8:zlib.compress(value,1) for k,value in list(layouts.items())})
    code=min(layouts,key=lambda k:(len(layouts[k]),k))
    data=layouts[code]
    raw=BASE.pack(b"R59"+bytes([code]),fence,bytes.fromhex(sha),len(ids),len(data))+data
    return raw+CRC.pack(zlib.crc32(raw))


def decode(blob, fence, sha):
    if len(blob)<HEADER or zlib.crc32(blob[:-4])!=CRC.unpack(blob[-4:])[0]:
        raise ValueError("invalid checkpoint checksum")
    magic,m,rev,count,size=BASE.unpack_from(blob)
    if magic[:3]!=b"R59" or m!=fence or rev!=sha or size!=len(blob)-HEADER or count>fence:
        raise ValueError("invalid checkpoint envelope")
    code=magic[-1]
    if code not in (0,1,2,3,4,8,9,10,11,12):
        raise ValueError("unknown checkpoint format")
    payload=blob[BASE.size:-4]
    if code>=8:
        try:
            payload=zlib.decompress(payload)
        except zlib.error as ex:
            raise ValueError("invalid compressed checkpoint") from ex
        code-=8
    bodies={}
    if code==COPY:
        pos=0
        ids=[]
        while pos<len(payload):
            j,pos=take_int(payload,pos,len(payload))
            size,pos=take_int(payload,pos,len(payload))
            if pos+size>len(payload):raise ValueError("truncated event body")
            body=unpack(payload[pos:pos+size])
            if len(set(body))!=len(body) or len(body)<2:raise ValueError("invalid event members")
            ids.append(j)
            bodies[j]=body
            pos+=size
    elif code==BITMAP:
        if len(payload)!=(fence+7)//8:raise ValueError("bad bitmap width")
        ids=[j for j in range(8*len(payload)) if payload[j//8] & (1<<(j%8))]
    else:
        items=unpack(payload)
        ids=list(items) if code==ABSOLUTE else [i-1 for i in accumulate(n+1 for n in items)]
        if code==EXCLUDED:
            holes=set(ids)
            if any(j>=fence for j in holes):raise ValueError("hole outside source")
            ids=[j for j in range(fence) if j not in holes]
    if len(ids)!=count or ids!=sorted(set(ids)) or any(j>=fence for j in ids):
        raise ValueError("invalid event references")
    return frozenset(ids),bodies

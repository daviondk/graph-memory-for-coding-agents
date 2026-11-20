"""Reversible layout of typed file → run → text edges. No labels or tool lookahead."""
import json, struct, sys, zlib
from pathlib import Path
from compression import zstd
from functools import lru_cache
import brotli
HERE=Path(__file__).resolve().parent
OLD=HERE.parents[1]/'graph_memory_round4'/'writer'
sys.path.insert(0,str(OLD/'anchor'))
import run_anchor as anchor
import memory
from shared import prior, read, rows, save, sha
DICT=memory.DICTIONARY
ZDICT=zstd.ZstdDict(DICT,is_raw=True)
LEVELS=['deflate3','deflate9','brotli4','brotli6','zstd8','zstd15']

def raw_text(state):
    arm,t,files,hist,last=state
    index=[]; body=[]
    for path,info,runs in files:
        edges=[]; end=0
        for start,step,lines in runs:
            edges.extend([start-end,t-step,len(lines)])
            end=start+len(lines)
            body.extend(lines)
        index.append([path,info,edges])
    # Escape reserved NUL and newlines in a single logical cell. A normal source
    # line stays byte-for-byte identical to the repository across encoder calls.
    escaped='\n'.join(s.replace('\0','\0z').replace('\n','\0n') for s in body)
    return prior.jsonbytes([arm,t,index,hist,last])+b'\n'+escaped.encode('utf8','surrogatepass')

def decode_text(raw):
    header,content=raw.split(b'\n',1)
    arm,t,index,hist,last=json.loads(header)
    stream=content.decode('utf8','surrogatepass').split('\n')
    ptr=0; files=[]
    for path,info,edges in index:
        end=0; runs=[]
        for j in range(0,len(edges),3):
            gap,age,count=edges[j:j+3]; start=end+gap
            lines=[s.replace('\0n','\n').replace('\0z','\0') for s in stream[ptr:ptr+count]]
            assert len(lines)==count; ptr+=count;end=start+count
            runs.append([start,t-age,lines])
        files.append([path,info,runs])
    assert ptr==len(stream) or (ptr==0 and stream==[''])
    return [arm,t,files,hist,last]

def compress(data,algo):
    if algo.startswith('deflate'):
        obj=zlib.compressobj(int(algo[7:]),zdict=DICT)
        return obj.compress(data)+obj.flush()
    if algo.startswith('brotli'):return brotli.compress(data,quality=int(algo[6:]))
    return zstd.compress(data,int(algo[4:]),zstd_dict=ZDICT)

def decompress(blob,algo):
    if algo.startswith('deflate'):
        obj=zlib.decompressobj(zdict=DICT); res=obj.decompress(blob)+obj.flush()
        assert obj.eof and not obj.unused_data
        return res
    if algo.startswith('brotli'):return brotli.decompress(blob)
    return zstd.decompress(blob,zstd_dict=ZDICT)

def encode(state,algo,layout):
    payload=prior.jsonbytes(state) if layout=='json' else raw_text(state)
    return b'R5'+bytes([LEVELS.index(algo)*2+int(layout=='edges')])+compress(payload,algo)

def decode(blob):
    assert blob[:2]==b'R5'
    method=blob[2];raw=decompress(blob[3:],LEVELS[method//2])
    return decode_text(raw) if method%2 else json.loads(raw)

def calibrate():
    from collections import Counter
    import hashlib, time
    totals=Counter();identifiers=[];timings=Counter();n=0
    for p in sorted((OLD/'anchor'/'factorial'/'C').glob('cuts_*.gz')):
        for iid,t,obj in rows(p):
            x=obj['cal_anchor']
            if not x[2] or int(hashlib.sha256(f'{iid}|{t}'.encode()).hexdigest()[:8],16)%16:continue
            for m in LEVELS:
                start=time.process_time()
                b=encode(x,m,'json');assert decode(b)==x
                timings[m]+=time.process_time()-start;totals[m]+=len(b)
            n+=1;identifiers.append([iid,t])
    assert n>30
    best=min(LEVELS,key=lambda k:totals[k])
    save(HERE/'dev.json',dict(n=n,ids=identifiers,total_bytes=totals,cpu_seconds=timings,best=best))
    print(best,n,totals)
if __name__=='__main__':calibrate()

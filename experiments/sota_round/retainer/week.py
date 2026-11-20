import json,gzip,zlib,struct,hashlib
import numpy as np
from collections import Counter
from fetch import byte_range, RAW, HERE, digest
from native import PAIR,run_s4
from study import build,replay,RESULTS,summarize
def main():
    src=json.loads((HERE/'sources.json').read_text())
    v=next(v for v in src['volumes'] if v['volume']=='hm_0')
    pos=v['zip_local_header'];h=struct.unpack_from('<4s5H3I2H',byte_range(pos,pos+511));start=pos+30+h[-2]+h[-1]
    packed=byte_range(start,start+v['zip_compressed_bytes']-1)
    raw=zlib.decompress(packed,-15)
    assert '%08x'%(zlib.crc32(raw)&0xffffffff)==v['zip_member_crc32']
    ranges=[]
    for row in raw.splitlines():
        ts,host,disk,kind,off,n,dt=row.split(b',')
        if kind==b'Read':
            x=int(off); y=int(n)
            ranges.append(range(x//4096,(x+y-1)//4096+1))
    n=len(ranges);cut=n//2;cap=512
    print('Full raw read count',n,'held-out',n-cut)
    pins=build(ranges[:cut],[cap])[cap]
    data=np.zeros(n,dtype=PAIR);data['oid']=[r.start for r in ranges];data['count']=[len(r) for r in ranges]
    stream=RAW/'hmweek.stream';data.tofile(stream)
    methods=[]
    for p in ('s4','s3','lru'): methods.append(run_s4('wholeweek_hm0',stream,cap,cut,p))
    for k in ('joint','marginal'):
        a=replay(ranges[cut:],pins[k],0,'none',0).astype('<u4')
        sha=digest(a.tobytes())
        (RESULTS/'steps'/(sha+'.gz')).write_bytes(gzip.compress(a.tobytes(),mtime=0))
        methods.append(dict(algo=k,**summarize(a),pin_groups=len({p//4 for p in pins[k]}),row_sha256=sha))
    report=dict(volume='hm_0',all_raw_rows=len(raw.splitlines()),read_count=n,fit_n=cut,evaluation_n=n-cut,capacity=cap,raw_sha256=digest(raw),methods=methods)
    (RESULTS/'whole_week.json').write_text(json.dumps(report,indent=2),encoding='utf8')
if __name__=='__main__':main()

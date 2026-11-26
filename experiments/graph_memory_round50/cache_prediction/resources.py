"""Round-trip actual bounded metadata and measure terminal CPU updates in alternating orders."""
import hashlib,struct,statistics,time
import numpy as np
from study import D,read,put,Cache,Keys,select,retention
SLOT=struct.Struct('<32s8sIIHHHBBQ');assert SLOT.size==64
PAYLOAD=4096*4
HEADER=256


def pack(res,m):
    coef=[m['intercept']]+m['coef']
    head=struct.pack('<4sBH','FM01'.encode(),len(coef),len(res))+struct.pack('<'+'d'*len(coef),*coef)
    buf=bytearray(head.ljust(HEADER,b'\0'))
    for i,(k,(o,seen,last)) in enumerate(res.items()):
        cost,path,a,b,test,py,obs=o;flags=test+2*py+4*obs
        buf.extend(SLOT.pack(bytes.fromhex(k),bytes.fromhex(path),a,b,cost,seen,last,flags,0,PAYLOAD*i))
    return bytes(buf)


def unpack(buf):
    magic,n,nn=struct.unpack_from('<4sBH',buf);assert magic==b'FM01'
    co=struct.unpack_from('<'+'d'*n,buf,7);res={}
    for i in range(nn):
        k,path,a,b,cost,seen,last,flags,_,ptr=SLOT.unpack_from(buf,HEADER+64*i);assert ptr==i*PAYLOAD
        res[k.hex()]=([cost,path.hex(),a,b,flags&1,(flags>>1)&1,(flags>>2)&1],seen,last)
    return res,dict(coef=list(co[1:]),intercept=co[0])


def make_baseline(hist,rows):
    pol=Cache('proposed',31,Keys())
    for p in hist:
        z=rows[p];pol.operate({k:z['docs'][k][0] for k in z['order']})
    return pol


def main():
    rows=read(D/'inputs.json.gz');obs=read(D/'outcomes.json.gz');models=read(D/'models.json')
    timings={};peak=0;checks=0;archive={}
    for q,z in rows.items():
        pr=z['prev'];bank=models[obs[q]['fold']];initial={}
        for m in ['graph','local']:
            cur={}
            for i,p in enumerate(pr):
                cur=select(cur,rows[p],i,bank[m],m=='graph')
            buf=pack(cur,bank[m]);un,coef=unpack(buf);assert un==cur and retention(un,z)==obs[q]['arms'][m] and coef['coef']==bank[m]['coef']
            initial[m]=(un,coef)
        results={'graph':[],'local':[],'proposed':[]};docs={k:z['docs'][k][0] for k in z['order']}
        order=['graph','local','proposed'];r=int(hashlib.sha256(q.encode()).hexdigest(),16)%3
        for rep in range(3):
            base=make_baseline(pr,rows);idx=(r+rep)%3
            for m in order[idx:]+order[:idx]:
                if m=='proposed':
                    t=time.perf_counter_ns();base.operate(docs);ns=time.perf_counter_ns()-t
                else:
                    un,coef=initial[m];t=time.perf_counter_ns();chosen=select(un,z,len(pr),coef,m=='graph');ns=time.perf_counter_ns()-t
                    if rep==0:
                        after=pack(chosen,coef);saved,again=unpack(after);assert saved==chosen and again==coef
                        size=len(after)+PAYLOAD*len(chosen);assert size<=524288;peak=max(peak,size);checks+=1
                        archive.setdefault(q,{})[m]=dict(keys=len(chosen),metadata=len(after),total=size,packed_sha256=hashlib.sha256(after).hexdigest())
                results[m].append(ns)
        timings[q]={k:int(statistics.median(v)) for k,v in results.items()}
    reports={}
    for panel in ['R48','R49']:
        qq=[q for q,x in rows.items() if x['panel']==panel];reports[panel]={m:dict(median_ms=float(np.median([timings[q][m] for q in qq])/1e6),p95_ms=float(np.percentile([timings[q][m] for q in qq],95)/1e6)) for m in ['graph','local','proposed']}
    put('packing.json.gz',archive);put('cpu-ns.json.gz',timings)
    put('resources.json',dict(roundtrips=checks,peak_total=peak,max_meta=HEADER+64*31,slot=SLOT.size,head=HEADER,vector_bytes=PAYLOAD,panels=reports))
    print(checks,peak,reports)


if __name__=='__main__':main()


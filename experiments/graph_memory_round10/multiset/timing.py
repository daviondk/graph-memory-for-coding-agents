from pathlib import Path
import gc,hashlib,json,os,platform,statistics,sys,time
import numpy as np
from common import ROOT,R9,ARMS,load,put
from structures import flat,sparse,xormap
from reader import read
sys.path.append(str(R9/'budget'))
import sketch
def measure(fn):
    fn()
    cpu0=time.process_time_ns(); wall0=time.perf_counter_ns();n=0
    while time.process_time_ns()-cpu0<125_000_000:
        for _ in range(4):fn()
        n+=4
    return {'n':n,'cpu_ns':(time.process_time_ns()-cpu0)/n,'wall_ns':(time.perf_counter_ns()-wall0)/n}
def main():
    files=sorted((ROOT/'old').rglob('*.json.gz'));by={}
    for p in files:
        d=load(p);by.setdefault(d['panel'],set()).add(d['issue'])
    chosen={t for pn,ids in by.items() for t in sorted(ids,key=lambda x:hashlib.sha256(('R10-time|'+x).encode()).digest())[:3]}
    recs=[]
    for p in files:
        o=load(p)
        if o['issue'] not in chosen:continue
        ss=[set(s) for s in o['sets']];n=len(ss)
        def prep():
            masks={}
            for i,vals in enumerate(ss):
                for s in vals:masks[s]=masks.get(s,0)|(1<<i)
            keys=sorted(masks);return keys,np.array([masks[k] for k in keys],dtype=np.uint16)
        prep_ns=measure(prep);keys,vals=prep()
        q=load(ROOT/'future'/p.parent.name/p.name)['changed'];cards=list(map(len,ss))
        states=load(ROOT/'states'/p.parent.name/p.name)['states']
        for b in [64,256]:
            cap=n*b
            def gen(method):
                if method=='r9':
                    sketch.addresses.cache_clear()
                    out=bytes([0,n,0])+sketch.encoded(sketch.layout(ss,cap-3)['selected'],0)
                    sketch.addresses.cache_clear()
                    return out
                if method=='flat_bloofi':return flat(n,0,cap,keys,vals,cards)[0]
                if method=='bucket':return flat(n,0,cap,keys,vals,cards,1)[0]
                if method=='sparse_dict':return sparse(n,0,cap,keys,vals,cards)[0]
                if method=='xor_map':return xormap(n,0,cap,keys,vals,cards)[0]
                x=sparse(n,0,cap,keys,vals,cards); y=xormap(n,0,cap,keys,vals,cards)
                return min([x,y],key=lambda z:(z[1]['risk'],z[1]['used']))[0]
            for arm in ARMS:
                payload=gen(arm)
                import base64
                archived=next(z for z in states if z['salt']==0 and z['b']==b and z['arm']==arm)
                assert payload==base64.b64decode(archived['data'])
                recs.append({'issue':o['issue'],'panel':p.parent.name,'direction':o['direction'],'b':b,'arm':arm,'common_preprocess':prep_ns,'write':measure(lambda:gen(arm)),'cold_payload_read':measure(lambda:read(payload,q))})
    summary={}
    for b in [64,256]:
        summary[b]={}
        for m in ARMS:
            rows=[r for r in recs if r['b']==b and r['arm']==m]
            summary[b][m]={'cases':len(rows),'write_cpu_ms':statistics.median(r['write']['cpu_ns'] for r in rows)/1e6,'read_cpu_us':statistics.median(r['cold_payload_read']['cpu_ns'] for r in rows)/1e3,'write_wall_ms':statistics.median(r['write']['wall_ns'] for r in rows)/1e6,'read_wall_us':statistics.median(r['cold_payload_read']['wall_ns'] for r in rows)/1e3}
    put(ROOT/'timing_results.json',{'issues':sorted(chosen),'platform':platform.platform(),'python':sys.version,'numpy':np.__version__,'clock':str(time.get_clock_info('process_time')),'summary':summary,'rows':recs})
    print(summary)
if __name__=='__main__':main()

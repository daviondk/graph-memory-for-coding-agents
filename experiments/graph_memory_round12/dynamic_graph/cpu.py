import base64,hashlib,statistics,time,tracemalloc,platform
from util12 import D,load,dump,digest
from write import frames,chunks
from store12 import ARMS,update,regions_read
from gcs import refresh,lookup
from dictionary import make,decode
def bench(fn):
    fn();start=time.process_time_ns();wall=time.perf_counter_ns();n=0
    while time.process_time_ns()-start<125000000:
        for _ in range(4):fn()
        n+=4
    return dict(n=n,cpu_us=(time.process_time_ns()-start)/n/1000,wall_us=(time.perf_counter_ns()-wall)/n/1000)
def peak(fn):
    tracemalloc.start()
    try:
        warm=tracemalloc.get_traced_memory()[0];ret=fn();top=tracemalloc.get_traced_memory()[1]
        return max(0,top-warm)
    finally:tracemalloc.stop()
def main():
    out=[]
    for p in sorted((D/'events').glob('*.gz')):
        native=load(p);t=native['task'];n=native['n'];events=native['events']
        ev=min((x for x in events if x['phase']==1),key=lambda x:digest('R12-cpu-event|'+t+'|'+str(x['step'])))
        target=ev['step'];r=ev['i'];words=ev['words'];archive,meta=frames(events,n);offsets=meta[target][0]
        def fetch(i):return chunks(archive,offsets[i])[0]
        q=min(load(D/'probes'/p.name)['keys'],key=lambda k:digest('R12-cpu-probe|'+t+k))
        native_states=load(D/'states'/p.name)['rows'];gcs=load(D/'gcs_states'/p.name);exact=load(D/'exact_states'/p.name)
        for b in (64,256):
            for a in ARMS+['gcs','mutable_exact']:
                if a in ARMS:
                    take=lambda j:next(base64.b64decode(x[6]) for x in native_states if x[0]==j and x[2:6]==[b,0,0,a])
                    old=take(target-1);new=take(target);write=lambda:update(old,r,words,fetch)[0]
                    parsed=lambda:regions_read(new);hot=parsed();cold=lambda:parsed()(q)
                elif a=='gcs':
                    take=lambda j:next(base64.b64decode(x[5]) for x in gcs if x[:5]==[j,int(j>=n),b,0,0])
                    old=take(target-1);new=take(target);write=lambda:refresh(old,r,words)[0]
                    parsed=lambda:lookup(new);hot=parsed();cold=lambda:parsed()(q)
                else:
                    take=lambda j:next(base64.b64decode(x[4]) for x in exact if x[:4]==[j,int(j>=n),b,0])
                    old=take(target-1);new=take(target);write=lambda:make(old,words,r,n,fetch,b*n,False)[0]
                    def parsed():
                        mp=decode(new);return (lambda q:new[2]) if mp is None else lambda q:mp.get(q,0)
                    hot=parsed();cold=lambda:parsed()(q)
                assert new==write() and cold()==hot(q)
                out.append(dict(task=t,step=target,arm=a,b=b,seed=0,key=q,write=bench(write),cold=bench(cold),hot=bench(lambda:hot(q)),write_heap_peak=peak(write),cold_heap_peak=peak(cold),held_old_bytes=len(old),held_new_bytes=len(new)))
    summary={}
    for b in [64,256]:
        for a in ARMS+['gcs','mutable_exact']:
            rs=[c for c in out if c['b']==b and c['arm']==a]
            summary[f'{b}/{a}']={key:statistics.median(z[key]['cpu_us'] for z in rs) for key in ['write','cold','hot']}
            summary[f'{b}/{a}'].update({key:statistics.median(z[key] for z in rs) for key in ['write_heap_peak','cold_heap_peak']})
    dump(D/'cpu_results.json',dict(platform=platform.platform(),clock=str(time.get_clock_info('process_time')),summary=summary,rows=out))
if __name__=='__main__':main()
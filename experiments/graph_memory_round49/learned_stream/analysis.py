"""Audit exact optimal packets and unchanged prefixes in measured paired states."""
from collections import Counter,defaultdict
import argparse,ctypes as ct,gzip,hashlib,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
import numpy as np
D=Path(__file__).resolve().parent
def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def put(p,x):
    raw=(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
    p.write_bytes(gzip.compress(raw,compresslevel=5,mtime=0) if p.suffix=='.gz' else raw)
def common(a,b):
    return next((j for j,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)))
def verify_dp(fn,tail,cap):
    n=len(tail);ci=(ct.c_int*n)(*(r[1] for r in tail));ui=(ct.c_int64*n)(*(r[2] for r in tail));bits=(ct.c_ubyte*n)()
    fn(n,cap,ci,ui,bits);return [row[0] for i,row in enumerate(tail) if bits[i]]
def state(cost,seq,u):
    head=[];pos=0;used=0
    for i in seq:
        if used+cost[i]>1024:break
        pos+=1;used+=cost[i];head.append(i)
    cap=2048-used
    tail=[(i,cost[i],v) for i,v in zip(seq[pos:],u[pos:]) if cost[i]<=cap]
    ready=sum(c for i,c,v in tail)<=cap
    cells=[0]
    for i,c,v in tail:cells.append(cells[-1]+cap-c+1)
    return head,cap,tail,ready,cells
def run(seed,fn):
    src=D/f'input-{seed}.json.gz';assert hashlib.sha256(src.read_bytes()).hexdigest()==read(D/f'sources-{seed}.json')['input']
    data=read(src);table={};wrong=[];cold=0
    for q,case in data.items():
        cost=case['cost'];chron={i:j for j,i in enumerate(case['chron'])};prev=None;out=[]
        for pct,at,seq,u,pub in case['states']:
            h,cap,t,ready,cells=state(cost,seq,u);rank={i:j for j,i in enumerate(seq)};current=dict(zip(seq,u))
            selected=h+([i for i,c,v in t] if ready else verify_dp(fn,t,cap))
            if selected!=pub:wrong.append([q,pct,selected,pub])
            asc=sorted(t,key=lambda r:chron[r[0]])
            ascr=[(*r,rank[r[0]]) for r in asc]
            if prev is None:cold+=0 if ready else cells[-1]
            else:
                prev_cap,pt,pready,pasc,pascr,old,ord0,at0=prev
                assert set(old)<=set(current)
                k=common(pt,t);j=common(pasc,asc);jr=common(pascr,ascr)
                denom=0 if ready else cells[-1]
                stocked=not pready and cap<=prev_cap and not ready
                def skip(n):return cells[n] if not ready else 0
                cs=[0]
                for i,c,v in asc:cs.append(cs[-1]+cap-c+1)
                changed=sum(v!=current[i] for i,v in old.items())
                oldr=[i for i in seq if i in old];reordered=sum(a!=b for a,b in zip(ord0,oldr))
                terminal=skip(k) if stocked and k==len(pt) else 0
                block=skip(max(k//16*16,k if k==len(pt) else 0)) if stocked else 0
                out.append([pct,at!=at0,len(old),len(current),changed,reordered,len(t),len(pt),ready,pready,k,j,jr,denom,skip(k),block,terminal,cs[j] if not ready else 0,cs[jr] if not ready else 0,prev_cap,cap])
            prev=cap,t,ready,asc,ascr,current,seq,at
        table[q]=[case['t'],out]
    fields=['to_pct','distinct_event','old_n','new_n','updated_old_utilities','reordered_old_positions','tail','old_tail','fit','old_fit','rank_prefix','chron_prefix','chron_prefix_with_abs_rank','full_cells','optimistic_rank','checkpoint16','last','optimistic_chron','chron_with_abs_rank','old_cap','cap']
    put(D/f'ledger-{seed}.json.gz',{'fields':fields,'rows':table,'different_q32_packets':wrong,'cold_cells':cold})
    print(seed,'states',len(data)*4,'Q32 mismatches',len(wrong),flush=True)
def summarize(seed):
    d=read(D/f'ledger-{seed}.json.gz');fields=d['fields'];groups=defaultdict(list)
    for t,triplet in d['rows'].values():
        for r in triplet:groups[t].append(dict(zip(fields,r)))
    obs=[a for g in groups.values() for a in g]
    def total(key):return sum(v[key] for v in obs)
    values={}
    for k in ('optimistic_rank','checkpoint16','last','optimistic_chron','chron_with_abs_rank'):
        xy=np.array([[sum(a[k] for a in g),sum(a['full_cells'] for a in g)] for g in groups.values()],dtype=float)
        rng=np.random.default_rng(49191);b=[]
        for j in range(20):
            s=xy[rng.integers(len(xy),size=(500,len(xy)))].sum(axis=1);b.extend(s[:,0]/s[:,1])
        values[k]=dict(ratio=float(xy[:,0].sum()/xy[:,1].sum()),ci=np.quantile(b,[.025,.975]).tolist(),events=sum(a[k]>0 for a in obs))
    work=[a for a in obs if a['full_cells']];changed=[a for a in work if a['updated_old_utilities'] or a['reordered_old_positions']]
    return dict(seed=seed,questions=len(d['rows']),trajectories=len(groups),comparisons=len(obs),full_scans=len(work),distinct_events=sum(a['distinct_event'] for a in obs),mismatch=len(d['different_q32_packets']),
                old_reweighted=total('updated_old_utilities'),old_total=total('old_n'),updates_with_changed_utility=sum(a['updated_old_utilities']>0 for a in obs),updates_with_reorder=sum(a['reordered_old_positions']>0 for a in obs),
                cold_cells=d['cold_cells'],full_cells=total('full_cells'),rates=values,active_with_zero_prefix=sum(a['rank_prefix']==0 for a in work),changed_active=len(changed),
                changed_active_upper=sum(a['optimistic_rank'] for a in changed)/sum(a['full_cells'] for a in changed),
                quantiles={k:np.quantile([a[k] for a in work],[0,.5,.9,1]).tolist() for k in ('tail','rank_prefix','chron_prefix')},
                recomputed_rank_tail_quantiles=np.quantile([a['tail']-a['rank_prefix'] for a in work],[0,.5,.9,1]).tolist(),
                cold_inclusive={k:total(k)/(total('full_cells')+d['cold_cells']) for k in values})
def main():
    cli=argparse.ArgumentParser();cli.add_argument('seeds',nargs='*',type=int);args=cli.parse_args()
    with tempfile.TemporaryDirectory(dir=D) as temp:
        dest=Path(temp)/('full.dll' if os.name=='nt' else 'full.so')
        subprocess.run(['g++','-O3','-std=c++17','-shared',*(['-fPIC'] if os.name!='nt' else ['-static-libgcc','-static-libstdc++']),str(D/'full.cpp'),'-o',str(dest)],check=True)
        dll_path=os.add_dll_directory(str(Path(shutil.which('g++')).resolve().parent)) if os.name=='nt' else None
        lib=ct.CDLL(str(dest));fn=lib.pick;fn.argtypes=[ct.c_int,ct.c_int,ct.POINTER(ct.c_int),ct.POINTER(ct.c_int64),ct.POINTER(ct.c_ubyte)]
        for seed in args.seeds or [13]:
            run(seed,fn);s=summarize(seed);put(D/f'summary-{seed}.json',s);print(s,flush=True)
        if os.name=='nt':
            import _ctypes;_ctypes.FreeLibrary(lib._handle)
if __name__=='__main__':main()

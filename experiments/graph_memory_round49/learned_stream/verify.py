"""Offline independent check of published lists, DP cell counts, and chronology diagnostics."""
from collections import Counter
import ctypes as ct,gzip,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
D=Path(__file__).resolve().parent
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def count_prefix(p,c):
    stop=0
    while stop<len(p) and stop<len(c) and p[stop]==c[stop]:stop+=1
    return stop
def floating(cost,order,values):
    prefix=[];w=2048
    for i in order:
        if w-cost[i]<1024:break
        prefix.append(i);w-=cost[i]
    ids=order[len(prefix):];gain=values[len(prefix):];mat=[];dp=[0.0]*(w+1)
    for i,v in zip(ids,gain):
        c=cost[i];take=bytearray(w+1)
        for j in range(w,c-1,-1):
            nv=dp[j-c]+v
            if nv>dp[j]:dp[j]=nv;take[j]=1
        mat.append(take)
    tail=[]
    for i,mask in reversed(list(zip(ids,mat))):
        if mask[w]:tail.append(i);w-=cost[i]
    return prefix+tail[::-1]
def check(seed,func):
    inputfile=D/f'input-{seed}.json.gz';src=read(D/f'sources-{seed}.json')
    assert src['input']==hashlib.sha256(inputfile.read_bytes()).hexdigest()
    data=read(inputfile);measured=read(D/f'ledger-{seed}.json.gz');summary=read(D/f'summary-{seed}.json')
    floats=read(D/f'float-audit-{seed}.json');witnesses={(q,c):v for q,c,v in floats['witnesses']}
    assert floats['q32_ledger_in_scope'] and floats['verified']==len(data)*4
    misses=[];sums=Counter();distinct_saved=0;count=0
    for q,case in data.items():
        chronology={ident:j for j,ident in enumerate(case['chron'])};cost=case['cost'];prev=None
        t,observed=measured['rows'][q];assert case['t']==t
        for idx,(percentage,ts,order,values,original) in enumerate(case['states']):
            rank={v:j for j,v in enumerate(order)};assert len(order)==len(rank)==len(values)
            k=0;w=2048
            while k<len(order) and w-cost[order[k]]>=1024:w-=cost[order[k]];k+=1
            rows=[(i,cost[i],v) for i,v in zip(order[k:],values[k:]) if cost[i]<=w]
            chrono=sorted(rows,key=lambda a:chronology[a[0]]);strict=[a+(rank[a[0]],) for a in chrono]
            ready=sum(a[1] for a in rows)<=w
            n=len(rows);cg=(ct.c_int*n)(*(v[1] for v in rows));ug=(ct.c_int64*n)(*(v[2] for v in rows));flags=(ct.c_ubyte*n)()
            if ready:actual=order[:k]+[a[0] for a in rows]
            else:
                func(n,w,cg,ug,flags);actual=order[:k]+[v[0] for v,f in zip(rows,flags) if f]
            if actual!=original:
                misses.append([q,percentage,actual,original]);assert floating(cost,order,witnesses[q,percentage])==original
            def cells(seq):return sum(w-c+1 for _,c,*_ in seq) if not ready else 0
            if prev:
                pt,oldw,oldready,oldc,olds,oldtime=prev
                m=count_prefix(pt,rows);j=count_prefix(oldc,chrono);sf=count_prefix(olds,strict)
                v=dict(zip(measured['fields'],observed[idx-1]));stock=(not oldready and oldw>=w)
                terminal=cells(rows[:m]) if stock and m==len(pt) else 0
                checkpoint=max(terminal,cells(rows[:(m//16)*16]) if stock else 0)
                chk={'full_cells':cells(rows),'optimistic_rank':cells(rows[:m]),'optimistic_chron':cells(chrono[:j]),'chron_with_abs_rank':cells(chrono[:sf]),'last':terminal,'checkpoint16':checkpoint}
                assert all(val==v[key] for key,val in chk.items())
                sums.update(chk);count+=1
                if oldtime<ts:distinct_saved+=checkpoint
            prev=rows,w,ready,chrono,strict,ts
    assert misses==measured['different_q32_packets'] and len(misses)==summary['mismatch']
    assert count==6000 and sums['full_cells']==summary['full_cells'] and distinct_saved==0
    for k in summary['rates']:assert sums[k]/sums['full_cells']==summary['rates'][k]['ratio']
    return len(misses)
def main():
    if (D/'manifest.json').exists():
        for n,s in read(D/'manifest.json')['files'].items():assert hashlib.sha256((D/n).read_bytes()).hexdigest()==s
    with tempfile.TemporaryDirectory() as name:
        path=Path(name)/('full.dll' if os.name=='nt' else 'full.so')
        subprocess.run(['g++','-O3','-std=c++17','-shared',*(['-static-libgcc','-static-libstdc++'] if os.name=='nt' else ['-fPIC']),str(D/'full.cpp'),'-o',str(path)],check=True)
        search=os.add_dll_directory(str(Path(shutil.which('g++')).resolve().parent)) if os.name=='nt' else None
        lib=ct.CDLL(str(path));fn=lib.pick;fn.argtypes=[ct.c_int,ct.c_int,ct.POINTER(ct.c_int),ct.POINTER(ct.c_int64),ct.POINTER(ct.c_ubyte)]
        total=sum(check(seed,fn) for seed in (13,17,29,37,41))
        assert total==3
        if os.name=='nt':
            import _ctypes;_ctypes.FreeLibrary(lib._handle)
    print('Verified 40,000 Q32 predictions, 3 float witnesses and diagnostic counts at 30,000 transitions.')
if __name__=='__main__':main()

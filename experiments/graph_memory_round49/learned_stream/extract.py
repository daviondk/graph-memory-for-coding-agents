"""Reproduce sealed R41 inputs and model outputs without consulting gold. Default to the registered seed."""
from pathlib import Path
import argparse,gzip,hashlib,json,os,sys
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1]
R=W/'graph_memory_round41/causal_budget'
def h(b):return hashlib.sha256(b).hexdigest()
def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def put(p,o):
    raw=(json.dumps(o,sort_keys=True,separators=(',',':'))+'\n').encode()
    p.write_bytes(gzip.compress(raw,compresslevel=6,mtime=0) if p.suffix=='.gz' else raw)
def main(seed):
    assert h((D/'PROTOCOL_RU.md').read_bytes())=='290329393fec3bc27ce64f7b08bce0a9bcc36d8ef0b2f046e4f4323fc48b64b3'
    sys.path.insert(0,str(R));import forecast_packets as f
    source=Path('D:/CodexResearch/x20-r33-budget-loss/test.json.gz')
    assert h(source.read_bytes())==read(W/'graph_memory_round33/budget_loss/test-input.json')['features']
    orig={v['q']:v for v in read(source)}
    model=read(W/'graph_memory_round39/global_packet/models.json')['models']['graph']
    rm=read(W/'graph_memory_round20/factor_reader/hash64-weights.json')['rank'] if seed==13 else read(W/f'graph_memory_round21/five_seed/seed-{seed}/calibration.json')['rank']
    live=D.parent/'stream_packet/input.json.gz';assert h(live.read_bytes())==read(live.parent/'input-seal.json')['file']
    chrono=read(live);out={};m=read(R/'manifest.json')['files'];sources={}
    func=f.packet.base.kernel();count=0; witnesses=[]
    recorded=D/f'ledger-{seed}.json.gz'
    differs={(q,p) for q,p,*_ in read(recorded)['different_q32_packets']} if recorded.exists() else set()
    for shard in range(8):
        a=R/f'state-{shard}.json.gz';b=R/f'pred-{seed}-{shard}.json.gz'
        for p in (a,b):
            sources[p.name]=h(p.read_bytes());assert sources[p.name]==m[p.name]
        expect={(q,pct):s['graph_dp'] for q,t,pct,pilot,s in read(b)}
        dense_db={} if seed==13 else {r['q']:r['dense'] for r in read(W/f'graph_memory_round21/five_seed/seed-{seed}/picks-{shard}.json.gz')}
        rows=[];X=[]
        for q,t,pct,at,ids,graph,pilot in read(a):
            key=h(q.encode());tr=h(t.encode());assert tr==chrono[key][0]==h(orig[q]['t'].encode())
            n=len(ids);ids=np.asarray(ids,dtype=int);z=np.asarray(orig[q]['x'])[ids].copy();ix={v:j for j,v in enumerate(ids)}
            dense=np.arange(n) if seed==13 else np.array([ix[j] for j in dense_db[q] if j in ix])
            offset=np.empty(n);offset[dense]=f.packet.base.linear(rm,f.packet.base.rankx(n));z[dense,0]=np.log1p(np.arange(1,n+1))
            x,order=f.packet.feature(z,np.asarray(graph),offset);X.append(x);rows.append((q,key,tr,pct,at,ids,order))
        gfloat=np.logaddexp(0,f.packet.portable(model,np.vstack(X)[:,model['cols']]))
        U=np.rint(gfloat*2**32).astype(np.int64)
        pos=0
        for q,key,tr,pct,at,ids,order in rows:
            g=U[pos:pos+len(ids)];dbl=gfloat[pos:pos+len(ids)];pos+=len(ids)
            prices=np.asarray(orig[q]['c'],dtype=int)[ids]
            restored=ids[f.packet.select(order,prices,dbl,1024,'dp',func)].tolist()
            assert restored==expect[q,pct],(q,pct);count+=1
            if (key,pct) in differs:witnesses.append([key,pct,dbl[order].tolist()])
            if key not in out:
                born=chrono[key][1];c=orig[q]['c']
                assert len(born)==len(c) and all(c[row[1]]==row[2] for row in born)
                out[key]=dict(t=tr,chron=[row[1] for row in born],cost=c,states=[])
            out[key]['states'].append([pct,at,ids[order].tolist(),g[order].tolist(),expect[q,pct]])
        assert pos==len(U)
    for v in out.values():
        v['states'].sort()
        assert [r[0] for r in v['states']]==[25,50,75,100]
    assert len(out)==2000 and len({v['t'] for v in out.values()})==1207
    dst=D/f'input-{seed}.json.gz'
    if dst.exists():assert read(dst)==out
    else:put(dst,out)
    put(D/f'float-audit-{seed}.json',{'verified':count,'witnesses':witnesses,'q32_ledger_in_scope':recorded.exists()})
    put(D/f'sources-{seed}.json',dict(input=h(dst.read_bytes()),source=sources,features=h(source.read_bytes()),chronology=h(live.read_bytes()),model=h((W/'graph_memory_round39/global_packet/models.json').read_bytes()),protocol=h((D/'PROTOCOL_RU.md').read_bytes())))
    print(seed,'extracted',len(out),'size',dst.stat().st_size,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('seeds',type=int,nargs='*');a=p.parse_args()
    for s in a.seeds or [13]:main(s)

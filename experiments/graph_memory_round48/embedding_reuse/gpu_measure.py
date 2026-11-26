"""Actual paired 8B GPU measurement. Offer no document unseen by the current or previous request."""
from inventory import *
import sys,time,os,socket,subprocess,re
import numpy as np,requests
R39=W/'graph_memory_round39/author_baseline';sys.path.insert(0,str(R39))
from reference import embed,EXE,NAME,DIGEST
def run_pair(pair,use_cache,st,inventory,tab,http,base):
    cached={};records=[];stats=[]
    for q in pair:
        row=st[q];dk=[v[0] for v in inventory[q]['docs']];keys=[None]+dk;tk=[tab[row['three']][1]]+[tab[k][1] for k in row['doc']]
        started=time.perf_counter();matrix=np.empty((len(tk),4096),dtype=np.float32);todo=[0];seen=set(cached);dup=set();inter=0;intra=0
        for i,k in enumerate(dk,1):
            if use_cache and k in seen:
                if k in cached:inter+=1
                else:intra+=1
                continue
            todo.append(i);seen.add(k)
        order=sorted(todo,key=lambda j:len(tk[j]));calls=0;elapsed=0.
        for x in range(0,len(order),4):
            batch=order[x:x+4];t=time.perf_counter();v=embed(http,base,[tk[j] for j in batch]);elapsed+=time.perf_counter()-t;matrix[batch]=v;calls+=1
        if use_cache:
            for j in todo:
                if j:cached[dk[j-1]]=matrix[j].copy()
            for j,k in enumerate(dk,1):matrix[j]=cached[k]
        scores=matrix[1:]@matrix[0];rank=np.argsort(-scores,kind='stable').tolist()
        stats.append(dict(misses=len(todo)-1,inter=inter,intra=intra,tokens=sum(len(tk[j]) for j in todo),calls=calls,query_tokens=len(tk[0]),docs=len(dk),embed_seconds=elapsed,wall=time.perf_counter()-started,cache_end=len(cached)))
        records.append((matrix,scores,rank))
    return stats,records
def main():
    assert os.environ.get('R48_CACHE_GPU_LEASE')=='1' and sha(D/'PROTOCOL_RU.md')==PROTO;sig=read(D/'input-seal.json')
    assert sha(D/'gpu-panel.json')==sig['gpu_panel'] and sha(TOK)==sig['source'] and sha(CACHE/NAME)==DIGEST==sig['config']['weights']
    z=read(TOK);states=z['states'];tab=z['tokens'];rows=read(D/'inventory.json.gz');pan=read(D/'gpu-panel.json')
    original=signed(R45,'qwen-scores.json.gz')|signed(CONF,'qwen-scores.json.gz')
    dest=CACHE/'r48-embedding-reuse';dest.mkdir(exist_ok=True);log=dest/'gpu-pairs.log'
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();http=requests.Session();http.trust_env=False;address='http://127.0.0.1:'+str(port)
    args=[str(EXE),'-m',str(CACHE/NAME),'-ngl','99','-fit','off','--embeddings','--pooling','last','-c','4096','-b','2048','-ub','2048','-t','3','-tb','3','-np','4','--host','127.0.0.1','--port',str(port),'--no-warmup','-lv','5']
    results=[];tick=time.perf_counter()
    with log.open('wb') as logfile:
        proc=subprocess.Popen(args,stdout=logfile,stderr=logfile,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES='0'))
        try:
            for _ in range(90):
                if proc.poll() is not None:raise RuntimeError('GPU process exited')
                try:
                    if http.get(address+'/health',timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(1)
            else:raise RuntimeError('GPU unavailable')
            warm=embed(http,address,[[301,659,151643]]);assert warm.shape==(1,4096)
            for ix,pair in enumerate(pan):
                ms={};rr={};modes=(False,True) if ix%2==0 else (True,False)
                for mode in modes:
                    k='cached' if mode else 'fresh';ms[k],rr[k]=run_pair(pair,mode,states,rows,tab,http,address)
                check=[]
                for j,q in enumerate(pair):
                    a,x,xr=rr['fresh'][j];b,y,yr=rr['cached'][j];ids=states[q]['ids'];oscore=np.array([original[q]['scores'][eid] for eid in ids])
                    diffs=np.max(np.abs(a-b),axis=1);cos=(a*b).sum(1)/np.sqrt((a*a).sum(1)*(b*b).sum(1))
                    check.append(dict(q=q,exact_vectors=int((diffs==0).sum()),total_vectors=len(diffs),max_coordinate=float(diffs.max()),min_cosine=float(cos.min()),max_score=float(np.max(np.abs(x-y))),
                        original_max_score=float(np.max(np.abs(oscore-x))),original_top8=[ids[i] for i in xr[:8]]==original[q]['ranks']['qwen'],fresh_scores=x.tolist(),cache_scores=y.tolist(),fresh_order=xr,cached_order=yr,
                        sameorder=[xr[:k]==yr[:k] for k in [5,8]],sameset=[set(xr[:k])==set(yr[:k]) for k in [5,8]]))
                results.append(dict(pair=pair,first_mode='cached' if modes[0] else 'fresh',runs=ms,check=check))
                print('GPU pair',ix+1,'of',len(pan),'complete.',flush=True)
        finally:proc.terminate();proc.wait(timeout=30)
    evidence=[l.strip() for l in log.read_text('utf8',errors='replace').splitlines() if re.search(r'offloaded [1-9][0-9]*/[0-9]+ layers to GPU|using device CUDA0|CUDA0 model buffer size|CUDA0 \(NVIDIA',l,re.I)]
    assert evidence;write('gpu-results.json.gz',results);write('gpu-seal.json',dict(results=sha(D/'gpu-results.json.gz'),source=sha(D/'input-seal.json'),program=sha(Path(__file__)),
          command=sha(D/'gpu.ps1'),model=DIGEST,backend=evidence,elapsed=time.perf_counter()-tick,log=sha(log)))
if __name__=='__main__':main()


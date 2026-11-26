"""Offline small Qwen cross-encoder on the prespecified full 12 x 16 comparison."""
from core import *
from fetch_small import CACHE,NAME,DIGEST
import os,socket,subprocess,requests
EXE=Path('D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe')
def main():
    assert sha(D/'RERANK_PROTOCOL_RU.md')=='7cea9af6694895aa95bdf5717a6533fd4090208ed6b1e71f1adad30818d8f995' and sha(CACHE/NAME)==DIGEST
    assert sha(D/'forecasts.json.gz')==read(D/'forecast-seal.json')['data']
    pp=read(D/'small-panel.json');rows=read(D/'forecasts.json.gz');x=read(TOK);tmp=socket.socket();tmp.bind(('127.0.0.1',0));port=tmp.getsockname()[1];tmp.close()
    args=[str(EXE),'-m',str(CACHE/NAME),'-dev','none','-ngl','0','--rerank','--pooling','rank','-np','1','-c','2048','-b','2048','-ub','2048','-t','4','-tb','4','--offline','--no-warmup','--host','127.0.0.1','--port',str(port),'-lv','3']
    cache={};out={};t=time.perf_counter();s=requests.Session();s.trust_env=False;base='http://127.0.0.1:'+str(port)
    def post(route,data):
        r=s.post(base+route,json=data,timeout=600)
        if not r.ok:raise RuntimeError((route,r.status_code,r.text[:360]))
        return r.json()
    def decode(k):
        if k not in cache:
            tt=x['tokens'][k][1][:-1];txt=post('/detokenize',{'tokens':tt})['content']
            # UTF-8 decoding can replace an incomplete last code point. Record the roundtrip, without exposing text.
            rt=post('/tokenize',{'content':txt,'add_special':False,'parse_special':False})['tokens']
            common=0
            for a,b in zip(tt,rt):
                if a!=b:break
                common+=1
            cache[k]=(txt,len(tt),len(rt),common)
        return cache[k]
    with (CACHE/'cpu-scorer.log').open('wb') as log:
        child=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1'))
        try:
            for _ in range(60):
                if child.poll() is not None:raise RuntimeError('CPU ranker exited; inspect cpu-scorer.log')
                try:
                    if s.get(base+'/health',timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(1)
            else:raise RuntimeError('CPU ranker health timeout')
            for q in pp:
                st=x['states'][q];ix=rows[q]['rank']['qwen'][:16];query=decode(st['three']);docs=[decode(st['doc'][i]) for i in ix];ts=time.perf_counter()
                pr=post('/v1/rerank',{'query':query[0],'documents':[v[0] for v in docs],'top_n':len(ix),'return_documents':False})
                result=pr['results'];assert sorted(z['index'] for z in result)==list(range(16))
                sc={ix[z['index']]:float(z['relevance_score']) for z in result};assert all(np.isfinite(list(sc.values())))
                out[q]=dict(indices=ix,scores=sc,rank=sorted(ix,key=lambda i:(-sc[i],ix.index(i)))+rows[q]['rank']['qwen'][16:],
                            token_roundtrips=[list(d[1:]) for d in [query,*docs]],usage=pr.get('usage'),seconds=time.perf_counter()-ts)
                print('CPU cross-encoder',len(out),'/12',round(out[q]['seconds'],1),'s',flush=True)
        finally:child.terminate();child.wait(timeout=25)
    assert len(out)==12
    write('reranker-scores.json.gz',out);write('reranker-seal.json',dict(data=sha(D/'reranker-scores.json.gz'),protocol=sha(D/'RERANK_PROTOCOL_RU.md'),model=DIGEST,
         shortlist=sha(D/'forecasts.json.gz'),panel=sha(D/'small-panel.json'),exe=sha(EXE),program=sha(D/'neural.py'),elapsed=time.perf_counter()-t,
         flags=[a for a in args[3:-4]],backend='CPU, 4 threads, CUDA disabled'))
if __name__=='__main__':main()

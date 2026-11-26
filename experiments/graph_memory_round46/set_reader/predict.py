from core import *
def main():
    t=time.perf_counter();assert sha(D/'PROTOCOL_RU.md')=='5438e46eb2986b24ea4268ea7af65a391f1eedd6c094e3598bd9f09c47db17f8'
    assert sha(TOK)==signed(P,'matched-token-seal.json')['forecasts_input'];x=read(TOK);p=signed(P,'panel.json');qwen=signed(P,'qwen-scores.json.gz');out={};gms={};tim=Counter();twelve=[]
    for q in sorted(p['remaining'],key=lambda i:hashlib.sha256(('r46-cross-check/'+i).encode()).digest()):
        if p['repo'][q] not in {p['repo'][v] for v in twelve}:twelve.append(q)
        if len(twelve)==12:break
    for q in p['order']:
        st=x['states'][q];ids=st['ids'];seen=st['seen'];s=qwen[q]['scores'];order=sorted(range(len(ids)),key=lambda i:(-s[ids[i]],ids[i]));G=cosine([x['tokens'][k][1] for k in st['doc']]);methods={'qwen':order,'qwen_mask':sorted(order,key=lambda i:seen[i])}
        assert ids==sorted(ids) and [ids[i] for i in order[:8]]==qwen[q]['ranks']['qwen']
        configs=[('dpp',.8,'dpp',None),('dpp_mask',.8,'dpp',seen),('history',.8,'history',seen),('historic_static',.8,'historic_static',seen),
         ('mmr',.8,'mmr',None),('mmr_mask',.8,'mmr',seen),('dpp_0',0,'dpp',None),('dpp_05',.5,'dpp',None),('dpp_095',.95,'dpp',None)]
        for name,beta,mode,mask in configs:
            a=time.perf_counter();methods[name]=rank(G,order,beta,mode,mask);tim[name]+=time.perf_counter()-a
        if q in twelve:methods['dpp_top16']=rank(G,order,.8,scope=order[:16])+order[16:]
        assert methods['qwen']==methods['dpp_0']
        assert not any(seen) or methods['dpp_mask'][0] in sorted(order,key=lambda i:seen[i])[:1]
        if not any(seen):assert methods['history']==methods['dpp']
        if len(ids)>1:assert methods['mmr'][:2]==methods['dpp'][:2]
        for val in methods.values():assert sorted(val)==list(range(len(ids)))
        out[q]=dict(ids=ids,seen=seen,rank=methods,repo=p['repo'][q],grams=hashlib.sha256(G.astype('<f8').tobytes()).hexdigest())
        # Six label-free, deterministic test states supply complete Gram matrices for independent determinant verification.
        if q in p['order'][:6]:gms[q]=G.tolist()
    write('small-panel.json',twelve);write('forecasts.json.gz',out);write('check-grams.json.gz',gms)
    write('forecast-seal.json',dict(data=sha(D/'forecasts.json.gz'),twelve=sha(D/'small-panel.json'),grams=sha(D/'check-grams.json.gz'),
           qwen=sha(P/'qwen-scores.json.gz'),tokens=sha(TOK),source=sha(P/'manifest.json'),program=sha(D/'predict.py'),core=sha(D/'core.py'),protocol=sha(D/'PROTOCOL_RU.md'),
           elapsed=time.perf_counter()-t,ranking_s=tim))
    print('Sealed',len(out),'complete public candidate pools, plus 12 small-panel lists.')
if __name__=='__main__':main()

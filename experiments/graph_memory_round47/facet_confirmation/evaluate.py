"""Score after all 101 predictions are sealed, using frozen public certificate and cost ordinals."""
from pathlib import Path
import hashlib,gzip,json,sys
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1];PR=D.parent/'facet_reader'
sys.path.insert(0,str(W/'memory_session5/serbench/upstream/src'))
from serbench import _reference_scorer as native
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(name,o):
    p=D/name;b=(json.dumps(o,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();p.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix=='.gz' else b)
METRICS=('CompleteMSS@5','CompleteMSS@8','CompleteMSS@8_2048','CompleteMSS@8_6144','GroupRecall@5','GroupRecall@8','Necessity@5','CompleteMSS_2048','CompleteMSS_6144')
NAMES=('qwen','union','qwen_mask','union_mask')
def outcome(indices,jud):
    selected=set(indices);groups=jud['groups'];h=[len(set(m)&selected)>=k for k,w,m in groups];w=sum(r[1] for r in groups)
    return [float(all(h) or any(set(a)<=selected for a in jud['alts'])),sum(h)/len(h) if h else 1.,sum(v*g[1] for v,g in zip(h,groups))/w if w else float(not h)]
def state(st,jud):
    arms={};cert=dict(required_evidence_groups=[dict(role=str(i),minimum_required=k,necessity_weight=w,acceptable_evidence_ids=arr) for i,(k,w,arr) in enumerate(jud['groups'])],alternative_minimal_sets=jud['alts'])
    orig=native.ideal_group_dcg;cache={}
    def denom(g,w,k):
        if k not in cache:cache[k]=orig(g,w,k)
        return cache[k]
    native.ideal_group_dcg=denom
    try:
        for name,index in st['rank'].items():
            cum=np.array(jud['cost'])[index].cumsum();n2,n6=[int((cum<=cap).sum()) for cap in (2048,6144)];lens=[5,8,min(8,n2),min(8,n6),n2,n6]
            v=[outcome(index[:k],jud) for k in lens]
            metrics=[s[0] for s in v[:4]]+[v[0][1],v[1][1],v[0][2],v[4][0],v[5][0]]
            for k,i in ((5,0),(8,1)):
                official=native.score_prediction(index[:k],cert,k)
                assert np.isclose(official[f'mss_complete@{k}'],metrics[i]) and np.isclose(official[f'group_recall@{k}'],metrics[4+i])
                if k==5:assert np.isclose(official['necessity_weighted_recall@5'],metrics[6])
            arms[name]=dict(metric=metrics,items=lens,tokens=[int(cum[k-1]) if k else 0 for k in lens])
    finally:native.ideal_group_dcg=orig
    return arms
def summarize(qs,data,pred):
    lookup=np.asarray([data[q]['repo'] for q in qs]);repos,idx=np.unique(lookup,return_inverse=True);freq=np.bincount(idx);n=len(repos)
    M=np.array([[data[q]['arms'][a]['metric'] for a in NAMES] for q in qs]);by=np.zeros((n,len(NAMES),len(METRICS)));np.add.at(by,idx,M);rm=by/freq[:,None,None]
    W=np.random.default_rng(471018).multinomial(n,np.repeat(1/n,n),size=20000);den=W@freq
    arms={};d={}
    for i,a in enumerate(NAMES):
        arms[a]=dict(counts=M[:,i].sum(0).tolist(),macro=rm[:,i].mean(0).tolist(),items=np.mean([data[q]['arms'][a]['items'] for q in qs],axis=0).tolist(),
                     tokens=np.mean([data[q]['arms'][a]['tokens'] for q in qs],axis=0).tolist())
    for i,j in ((3,2),(1,0)):
        a,b=NAMES[i],NAMES[j];dv=M[:,i]-M[:,j];dr=by[:,i]-by[:,j];mr=rm[:,i]-rm[:,j]
        d[a+' minus '+b]=dict(micro=dv.mean(0).tolist(),macro=mr.mean(0).tolist(),ci=np.quantile((W@dr)/den[:,None],[.025,.975],axis=0).tolist(),
            macroci=np.quantile((W@mr)/n,[.025,.975],axis=0).tolist(),wins=(dv>1e-10).sum(0).tolist(),loss=(dv< -1e-10).sum(0).tolist(),
            changed_set=[sum(set(pred[q]['rank'][a][:k])!=set(pred[q]['rank'][b][:k]) for q in qs) for k in (5,8)])
        d[a+' minus '+b]['repo_delta_primary']={repo:{'n':int(freq[z]),'net':int(dr[z,1])} for z,repo in enumerate(repos)}
    return dict(states=len(qs),repos=n,arms=arms,contrasts=d)
def main():
    seal=read(D/'forecast-seal.json');assert sha(D/'predictions.json.gz')==seal['pred'] and sha(D/'qwen-scores.json.gz')==seal['raw'] and sha(D/'anchor.json')==seal['anchor']
    p=read(D/'predictions.json.gz');p47=read(PR/'manifest.json');assert sha(PR/'ordinal-judgments.json.gz')==p47['files']['ordinal-judgments.json.gz']
    assert sha(PR/'manifest.json')==seal['sig']['previous'];ordinals=read(PR/'ordinal-judgments.json.gz');pan=read(PR/'panels.json');feats=read(W/'graph_memory_round34/external_transfer/features.json.gz')
    assert set(p)==set(pan['dev']) and set(p)==set(seal['order']) and len(p)==101
    repos={k:{feats[q]['repo'] for q in pan[k]} for k in ('train','dev','outside')};assert [len(repos[k]) for k in ('train','dev','outside')]==[68,34,69]
    for x,y in [('train','dev'),('train','outside'),('dev','outside')]:assert not repos[x]&repos[y]
    j={q:ordinals[q] for q in p};res={q:dict(repo=z['repo'],arms=state(z,j[q])) for q,z in p.items()};dump('outcomes.json.gz',res);dump('ordinal-judgments.json.gz',j)
    summary=summarize(seal['order'],res,p);raw=read(D/'qwen-scores.json.gz')
    dump('results.json',dict(summary=summary,metrics=METRICS,outcomes=sha(D/'outcomes.json.gz'),ordinals=sha(D/'ordinal-judgments.json.gz'),scorer=sha(Path(native.__file__)),forecast=sha(D/'forecast-seal.json'),
        all_ranked=sum(len(v['ids']) for v in p.values()),input_tokens=sum(v['tokens'] for v in raw.values()),embedding_seconds=sum(v['seconds'] for v in raw.values()),native_prefixes=2*len(p)*len(NAMES),
        repos={k:sorted(v) for k,v in repos.items()}))
    print('Measured',len(p),'states and',n_show(summary),'additional complete sets.')
def n_show(summary):return int(summary['arms']['union_mask']['counts'][1]-summary['arms']['qwen_mask']['counts'][1])
if __name__=='__main__':main()


"""Profile local read-side overhead independently of score labels or GPU inference."""
from train_model import *
from features import features,describe,decoder,TOK
from time import perf_counter
import platform,os
def main():
    # One thread. Timings describe this CPU run with concurrent GPU queue, with tokens in RAM.
    times={};counts={}
    tok=read(TOK);vocab=decoder();panel=read(BASE/'panels.json')['dev'];probs=read(D/'probabilities.json.gz');models=read(D/'models.json')
    full=read(BASE/'model.json')['candidate'];full={**full,'beta':[full['beta'][-1]],'inter':[full['inter'][-1]]};allm={**models['models'],'full':full};cols={**models['schema'],'full':list(range(109))}
    cache={};featurize=[];rows={};distinct=0;n=0
    def dec(k):return b''.join(vocab[i] for i in tok['tokens'][k][1][:-1]).decode('utf8',errors='replace')
    for q in panel:
        x=tok['states'][q];t=perf_counter()
        for k in x['doc']:
            if k not in cache:cache[k]=describe(dec(k));distinct+=1
        xx,_,_=features(dec(x['three']),[cache[k] for k in x['doc']]);rows[q]=xx.astype('float32').round(6).astype('float64')
        featurize.append(perf_counter()-t);n+=len(xx)
    for key,m in allm.items():
        mu,sd,b,inter=np.asarray(m['mu']),np.asarray(m['sd']),np.asarray(m['beta'][0]),m['inter'][0];x={q:xx[:,cols[key]] for q,xx in rows.items()};lat=[]
        for repetition in range(8):
            total=0.
            for q,xx in x.items():
                t=perf_counter();scores=1./(1.+np.exp(-np.clip(((xx-mu)/sd)@b+inter,-50,50)));total+=perf_counter()-t
                if repetition==0:assert np.allclose(scores,probs[q][key],rtol=0,atol=1e-12)
            if repetition:lat.append(total)
        times[key]={'all_seconds_by_repetition':lat,'median_ms_per_state':float(1000*np.median(lat)/len(panel)),'feature_count':len(cols[key])}
    dump('cost-audit.json',dict(states=len(panel),candidates=n,distinct_excerpts=distinct,derived_token_field_seconds=sum(featurize),
          field_ms_per_state=1000*sum(featurize)/len(panel),field_median_ms=float(1000*np.median(featurize)),inference=times,
          omp=os.environ.get('OMP_NUM_THREADS'),openblas=os.environ.get('OPENBLAS_NUM_THREADS'),platform=platform.platform(),
          exclusions=['data I/O, GPU/Qwen ranking, original tokenization; feature step starts from R45 token IDs and memoizes per distinct excerpt','model timing includes linear evaluation and normalization of feature columns; excludes ranking, feature extraction and setup']))
    print('Recorded token-to-feature and feature-to-probability latency for all',len(panel),'dev states.')
if __name__=='__main__':main()


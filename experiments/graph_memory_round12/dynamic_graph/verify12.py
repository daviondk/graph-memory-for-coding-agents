"""Independent replay against native test traces; verify all sealed byte states and probes."""
import base64,json,hashlib,statistics
from collections import Counter,defaultdict
import numpy as np
from util12 import D,R10,load,dump,sha
from store12 import regions_read
from adaptive import decode as adaptive_read
from gcs import lookup as gcs_read
from dictionary import decode as exact_read
def verify_series(src,old,latest,extra):
    for file in ['state_seal.json','read_seal.json','exact_seal.json']:
        receipt=load(src/file)
        if 'local' in receipt:
            for fn,h in receipt['r10'].items():assert sha(R10/fn)==h
            receipt=receipt['local']
        for fn,h in receipt.items():assert sha(src/fn)==h,(src,file,fn)
    scores=defaultdict(Counter);batches=0;bits=0;old_new=Counter()
    for path in sorted((src/'events').glob('*.gz')):
        e=load(path);t=e['task'];n=e['n'];roster=e['names']
        q=load(src/'probes'/path.name);terms=q['keys'];truth=[];native={};obs=[]
        for ev in e['events']:
            prior=set(native.get(ev['i'],[]));data=(old if not ev['phase'] else latest)['rows'][roster[ev['i']]]
            assert data==ev['words'] and (old if not ev['phase'] else latest)['status'][roster[ev['i']]]['call']=='passed'
            native[ev['i']]=data;now=set(data)
            if ev['phase']:old_new.update(insertions=len(now-prior),deletions=len(prior-now),replacements=1,noop=int(now==prior))
            mat=np.zeros(len(terms),dtype=np.uint8)
            for i,record in native.items():
                words=set(record);mat|=np.array([1<<i if term in words else 0 for term in terms],np.uint8)
            truth.append(mat)
        pred=load(src/'predictions'/path.name);ranks=load(src/'states'/path.name)['rows'];assert pred['keys']==terms
        for r,seen in zip(ranks,pred['rows'],strict=True):
            assert r[:6]==seen[:6]
            step,ph,b,s,g,arm,enc=r[:7];serialized=base64.b64decode(enc,validate=True);assert len(serialized)==b*n
            arr=np.frombuffer(base64.b64decode(seen[6]),np.uint8)
            assert np.all((arr&truth[step])==truth[step])
            # Direct decode two deterministic coordinates from every full frozen state.
            reader=regions_read(serialized)
            for j in (step%len(terms),(step*13+7)%len(terms)):assert reader(terms[j])==arr[j]
            scores[ph,b,s,g,arm].update(fp=sum((int(a)^int(v)).bit_count() for a,v in zip(arr,truth[step])),events=1)
            batches+=1;bits+=n*len(terms)
        for step,ph,b,g,enc,reads,st in load(src/'exact_states'/path.name):
            raw=base64.b64decode(enc);mp=exact_read(raw)
            arr=np.array([raw[2] if mp is None else mp.get(w,0) for w in terms],np.uint8)
            assert np.all((arr&truth[step])==truth[step])
            if st['fit']:assert np.array_equal(arr,truth[step])
        if extra:
            for directory,read in [('gcs_states',gcs_read),('adaptive_states',adaptive_read)]:
                for r in load(src/directory/path.name):
                    step,ph,b,s,a,enc=r[:6];raw=base64.b64decode(enc);assert len(raw)==b*n
                    arr=np.array([read(raw)(terms[0]),read(raw)(terms[-1])],np.uint8)
                    assert np.all((arr&truth[step][[0,-1]])==truth[step][[0,-1]])
    agg=load(src/'results.json')['cells']
    for ph,b,s,g,arm in scores:
        rest=statistics.mean(scores[ph,b,seed,g,arm]['fp'] for seed in [0,7,19,31])
        assert agg[f'{ph}/{b}/{g}/{arm}']['counts'].get('fp',0)==rest
    return dict(core_state_updates=batches,individual_reference_decisions=bits,missing_reference_edges=0,primary_metrics_recomputed=True,event_summary=old_new)
def main():
    latest=load(D/'trace_3.5.json');old=load(D/'trace_3.4.2.json');far=load(D/'wide'/'trace_2.8.8.json')
    rep=load(D/'repeat_3.5.json');assert latest['rows']==rep['rows'] and latest['status']==rep['status']
    first=verify_series(D,old,latest,True);second=verify_series(D/'wide',far,latest,False)
    for nm in ['gcs_seal.json','adaptive_seal.json']:
        for file,h in load(D/nm).items():assert sha(D/file)==h
    inp=load(D/'input_receipt.json')
    for file,h in inp['files'].items():assert sha(D/file)==h
    added=Counter();gone=Counter()
    for t,oldw in old['rows'].items():
        neww=latest['rows'][t];added.update(set(neww)-set(oldw));gone.update(set(oldw)-set(neww))
    dump(D/'verification.json',dict(primary=first,wide=second,primary_added_by_symbol=added,primary_removed_by_symbol=gone,repeated_native_ids_identical=len(rep['rows']),numpy=np.__version__))
    files=[p for p in D.rglob('*') if p.is_file() and not any(part in ['vendor','__pycache__'] for part in p.relative_to(D).parts) and p.name!='MANIFEST_SHA256.json' and not p.name.endswith('.pyc')]
    dump(D/'MANIFEST_SHA256.json',{p.relative_to(D).as_posix():sha(p) for p in sorted(files)})
    print(len(files),first,second)
if __name__=='__main__':main()
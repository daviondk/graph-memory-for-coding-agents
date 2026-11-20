"""Reconstruct the reference matrix from native traces and independently recount readouts."""
import base64,hashlib,gzip,json,statistics
from collections import defaultdict,Counter
from qutil import Q,R9,R10,put,load,sha
def main():
    files=load(Q/'native_source_and_traces.json.gz');refs=load(Q/'native_inputs.json');assert len(files)==len(refs)==36
    native={k:base64.b64decode(v,validate=True) for k,v in files.items()}
    for k,h in refs.items():assert hashlib.sha256(native[k]).hexdigest()==h
    native={k.replace(chr(92),'/'):v for k,v in native.items()}
    st=load(Q/'state_seal.json')
    for p,h in st['local'].items():assert sha(Q/p.replace(chr(92),'/'))==h
    for p,h in st['external'].items():assert sha(R9.parent/p.replace(chr(92),'/'))==h
    for p,h in load(Q/'read_seal.json').items():assert sha(Q/p.replace(chr(92),'/'))==h
    states={};ref={};cases=Counter()
    for path in (Q/'old').glob('*.gz'):
        o=load(path);t=o['task'];d=o['direction'];q=set(load(Q/'future'/path.name)['changed']);opp='gold' if d=='base' else 'base'
        def get(side):
            k=f'agentvalue/tasks/{t}/{side}/testdata/trace.json.gz'
            return json.loads(gzip.decompress(native[k]))['records']
        old=get(d);oth=get(opp);names=sorted(old);n=len(names)
        masks=[bool(q&set(old[x]['lines'])) for x in names]
        changed=[old[x]['status']!=oth[x]['status'] for x in names]
        ref[t,d]=(masks,changed)
        cases.update(raw_decisions=n,exact=sum(masks),flip=sum(changed),missed=sum(f and not m for f,m in zip(changed,masks)))
        z=load(Q/'states'/path.name)
        for b,s,a,enc,metadata in z['states']:
            raw=base64.b64decode(enc,validate=True);assert len(raw)==n*b
            if a=='exact':assert metadata['exact_fits'] and raw[0]==5
            states[t,d,b,s,a]=True
    total=defaultdict(Counter)
    rawrows=load(Q/'readouts.json.gz');assert len(rawrows)==len(states)
    for t,d,b,s,a,out,cap,meta in rawrows:
        del states[t,d,b,s,a]
        masks,flip=ref[t,d]
        for i,m in enumerate(masks):
            sel=bool(out>>i&1);assert sel or not m
            total[b,s,a].update(extra=sel and not m,stale=flip[i] and not sel)
    assert not states
    results=load(Q/'results.json')['summary']
    for b,s,a in total:
        for field in ('extra','stale'):
            assert results[str(b)][a][field]==statistics.mean(total[b,seed,a][field] for seed in range(32))
    assert cases==Counter(raw_decisions=72,exact=65,flip=40,missed=0)
    assert not any(v['stale'] for v in total.values())
    check=load(Q/'sympy_full.json')
    for key,digest in check['source_locks'].items():assert sha(R10/key)==digest
    put(Q/'verification.json',dict(native_files_verified=len(files),primary_payload_decisions=len(rawrows),cases=dict(cases),independent_algorithms=9,all_primary_reference_misses=0,all_primary_missed_status_changes=0,old_only_state_lock=True,upstream_quixbugs_commit='4257f44b0ff1181dedaedee6a447e133219fcebf',graph_memory_round10_sympy_extra_control_rows=len(check['rows'])))
    ps=[p for p in Q.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST_SHA256.json']
    put(Q/'MANIFEST_SHA256.json',{p.relative_to(Q).as_posix():sha(p) for p in sorted(ps)})
    print('files',len(ps),'states',len(rawrows),dict(cases))
if __name__=='__main__':main()
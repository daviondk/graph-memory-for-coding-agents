"""Score all matched arms after completed hardware measurements, retaining exact paired repository timing."""
from panel import *
import numpy as np,sys,itertools
sys.path.insert(0,str(W/'memory_session5/serbench/upstream/src'))
from serbench import _reference_scorer as native
ARMS=('fresh','proposed','lru','gdsf');MEASURES=('wall_rank','wall_commit','rpc_wall','compute_engine_s','tokenizer_wall','tokens','calls')
def labels(selected):
    with gzip.open(PUB/'labels.jsonl.gz','rt',encoding='utf8') as f:return {z['state_id']:z for z in map(json.loads,f) if z['state_id'] in selected}
def numeric(allm,field,control,boot):
    vals=np.asarray([[z[arm][field] for arm in ARMS] for z in allm]);a=ARMS.index('proposed');b=ARMS.index(control);x=vals[:,a];y=vals[:,b];safe=(boot@y)>0
    effect=1-x.sum()/y.sum() if y.sum()>0 else None;dist=1-(boot[safe]@x)/(boot[safe]@y) if safe.any() else np.array([])
    return dict(saving=effect,seconds_or_units=float(y.sum()-x.sum()),ci=np.quantile(dist,[.025,.975]).tolist() if len(dist) else None,wins=int((x<y).sum()),loss=int((x>y).sum()),
                mean_pair_ratio=float(np.mean(1-x/y)) if np.all(y>0) else None,pairs=[[float(u),float(v)] for u,v in zip(x,y)])
def main():
    p=read(D/'panel.json');seal=read(D/'run-seal.json');assert seal['raw']==sha(D/'raw-runs.json.gz') and seal['sig']['panel']==sha(D/'panel.json')
    data=read(D/'raw-runs.json.gz');states={q for z in p['selected'] for q in z['seq']};lab=labels(states);assert len(states)==len(lab)==24
    chainstats={};checks={};ords={};counters=defaultdict(int);drift=defaultdict(float);absg=defaultdict(int)
    for z in p['selected']:
        repo=z['repo'];arm=data[repo];scores={a:{} for a in ARMS};tot={a:Counter() for a in ARMS}
        for i,q in enumerate(z['seq']):
            ref=arm['fresh'][i];ids=ref['ids'];index={k:j for j,k in enumerate(ids)};truth=lab[q]
            ords[q]=dict(groups=[[g['minimum_required'],g['necessity_weight'],[index[k] for k in g['acceptable_evidence_ids'] if k in index]] for g in truth['required_evidence_groups']],
                        alternatives=[[index[k] for k in u] for u in truth['alternative_minimal_sets'] if all(k in index for k in u)])
            for name in ARMS:
                run=arm[name][i];rank=run['rank'];assert run['ids']==ids and run['q']==q and sorted(rank)==list(range(len(ids)))
                assert rank==np.argsort(-np.array(run['scores']),kind='stable').tolist() and run['wall_commit']>=run['wall_rank']>=run['rpc_wall'] and run['persistent_bytes']<=524288
                if name!='fresh':assert run['tokens']<=ref['tokens'] and len(run['resident_out'])<=31
                same_order=[rank[:k]==ref['rank'][:k] for k in (5,8)];same_set=[set(rank[:k])==set(ref['rank'][:k]) for k in (5,8)]
                certs=[];group=[]
                for k in (5,8):
                    off=native.score_prediction([ids[j] for j in rank[:k]],truth,k);certs.append(off[f'mss_complete@{k}']);group.append(off[f'group_recall@{k}'])
                exact=sum(x==y for x,y in zip(run['vector_sha'],ref['vector_sha']));err=max(abs(x-y) for x,y in zip(run['scores'],ref['scores']))
                scores[name][q]=dict(mss=certs,group=group,order=same_order,sets=same_set,full=rank==ref['rank'],vector_exact=exact,vectors=len(run['vector_sha']),max_score_error=err)
                for field in MEASURES:tot[name][field]+=run[field]
                counters[name+':vectors']+=len(run['vector_sha']);counters[name+':exact']+=exact;counters[name+':fullorder']+=rank==ref['rank']
                for k,m in enumerate(certs):absg[name+':mss'+str(5 if k==0 else 8)]+=int(m)
                drift[name]=max(drift[name],err)
        chainstats[repo]=tot;checks[repo]=scores
    put('ordinal-judgments.json.gz',ords);put('quality.json.gz',checks)
    repos=[z['repo'] for z in p['selected']];allm=[chainstats[z] for z in repos];n=len(repos)
    boot=np.random.default_rng(490731).multinomial(n,np.repeat(1/n,n),size=20000);contrasts={};totals={a:{k:sum(w[a][k] for w in allm) for k in MEASURES} for a in ARMS}
    for b in ('lru','gdsf','fresh'):
        cc={k:numeric(allm,k,b,boot) for k in MEASURES};contrasts['proposed vs '+b]=cc
    put('results.json',dict(chains=len(repos),states=len(states),documents=sum(len(dat['ids']) for a in data.values() for dat in a['fresh']),chain_totals=chainstats,totals=totals,
        contrasts=contrasts,quality=dict(counters),mss=dict(absg),max_score_error=drift,seal=sha(D/'run-seal.json'),quality_hash=sha(D/'quality.json.gz'),gold_hash=sha(D/'ordinal-judgments.json.gz'),official=sha(Path(native.__file__))))
    print('Scored',len(states),'states. Primary savings',[(c,contrasts[c]['wall_rank']['saving'],contrasts[c]['wall_rank']['ci']) for c in ('proposed vs lru','proposed vs gdsf')])
if __name__=='__main__':main()


"""Re-evaluate the frozen hybrid on checkpoints selected for the comparison metric."""
from pathlib import Path
import os, sys
for var in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[var]='1'
D=Path(__file__).resolve().parent
W=D.parents[1]
CURVE=W/'graph_memory_round39/budget_curve'
DEV=W/'graph_memory_round34/dev_metric'
PRIVATE=Path('D:/CodexResearch/x20-r34-dev-metric')
sys.path.insert(0,str(CURVE))
import predict as ref
from common import read,save,sha,SEEDS
np=ref.np if hasattr(ref,'np') else ref.packet.np
ARMS=('full_rgcn','wo_chunk_adjacency')
RULES=('strict','firstfit','dp','value')

def forecast(seeds):
    assert sha(D/'PROTOCOL_RU.md')=='1a8edda1a7dd733e627c8b531e7878a002f466a14afe59592d4636ef1c493758'
    choices=read(DEV/'all-dev-seal.json')
    assert len(choices)==10 and all(sha(DEV/file)==dig for file,dig in choices.items())
    split=W/'graph_memory_round19/trained_rank'
    mapping={r['q']:{item['node_id']:i for i,item in enumerate(r['rr'])} for j in range(8) for r in read(split/f'forecasts-main-{j}.json.gz')}
    assert len(mapping)==2000
    model=read(ref.GLOBAL/'models.json')['models']['graph']
    assert read(ref.GLOBAL/'dev-selection.json')['thresholds']['graph']==1024
    solve=ref.packet.base.kernel()
    for seed in seeds:
        dest=D/f'packets-{seed}.json.gz'
        if (D/f'forecast-{seed}.json').exists():
            assert read(D/f'forecast-{seed}.json')['data']==sha(dest)
            continue
        reg,x=ref.packet.projections('test',seed)
        u=np.logaddexp(0,ref.packet.portable(model,x[:,model['cols']]))
        stored={};data={};receipts={}
        for arm in ARMS:
            r=read(DEV/f'test-rank-seal-{seed}-{arm}.json')
            path=PRIVATE/f'seed-{seed}'/arm/'test-ranks.json.gz'
            assert r['ranks']==sha(path) and r['dev']==sha(DEV/'all-dev-seal.json')
            data[arm]=read(path)
            assert set(data[arm])==set(reg)==set(mapping)
            receipts[arm]=r
        for q,(t,c,_,__,sl) in reg.items():
            packs={}
            for arm in ARMS:
                ranked=np.array([mapping[q][n] for n in data[arm][q]])
                assert np.array_equal(np.sort(ranked),np.arange(len(c)))
                strict,ff,dp=ref.packs(ranked,c,u[sl],solve,2048)
                k=int(c[ranked].cumsum().searchsorted(1024,side='right'))
                head=ranked[:k];remaining=2048-int(c[head].sum())
                tail=ranked[k:];tail=tail[np.argsort(-u[sl][tail],kind='stable')]
                value=head.tolist()
                for idx in tail:
                    if int(c[idx])<=remaining:
                        value.append(int(idx));remaining-=int(c[idx])
                for name,p in zip(RULES,(strict,ff,dp,value)):
                    assert len(set(p))==len(p) and c[p].sum()<=2048
                    packs[arm+'/'+name]=p
            stored[q]=[t,packs]
        save(dest,stored)
        save(D/f'forecast-{seed}.json',dict(data=sha(dest),code=sha(Path(__file__)),protocol=sha(D/'PROTOCOL_RU.md'),
            model=sha(ref.GLOBAL/'models.json'),selection=sha(ref.GLOBAL/'dev-selection.json'),checkpoints=receipts))
        print('sealed',seed,len(stored),flush=True)

def grade():
    import sys
    sys.path.insert(0,str(W/'graph_memory_round33/budget_loss'))
    import data as src
    seals={s:sha(D/f'forecast-{s}.json') for s in SEEDS}
    save(D/'forecast-complete.json',dict(seeds=seals,code=sha(Path(__file__))))
    atoms=read(W/'graph_memory_round34/interval_witness/test-atoms.json.gz')
    truth=read(src.nm.OFF/'gold-spans.json.gz')
    refrows={s:{a:read(DEV/f'test-results-{s}-{a}.json.gz') for a in ARMS} for s in SEEDS}
    allpacks={}
    for s in SEEDS:
        path=D/f'packets-{s}.json.gz'
        assert read(D/f'forecast-{s}.json')['data']==sha(path)
        allpacks[s]=read(path)
    result=[];nchecked=0
    for path in src.sources('test'):
        for r in read(path):
            q,t=r['q'],r['t']
            gold=tuple(src.nm.pilot.SourceSpan.model_validate(sp) for sp in truth[q])
            nodes=[src.nm.pilot.RankedNodeRecord.model_validate(x) for x in r['rr']]
            spans=[(b-a,set(ids)) for _,a,b,ids in atoms[q]]
            total=sum(w for w,_ in spans);cache={};each={}
            for s in SEEDS:
                ts,rows=allpacks[s][q];assert ts==t
                vals={}
                for name,ids in rows.items():
                    key=tuple(ids)
                    if key not in cache:
                        observed=set(ids);covered=sum(w for w,v in spans if v&observed)
                        chosen=tuple(nodes[j] for j in ids);cost=sum(item.token_count for item in chosen)
                        measured=src.nm.pilot.span_metrics_under_token_budget(chosen,gold,2048)
                        assert len(observed)==len(ids) and cost<=2048 and (covered==total)==measured.full_support and abs(covered/total-measured.coverage)<1e-12
                        cache[key]=[int(covered==total),covered/total,cost]
                    vals[name]=cache[key]
                for arm in ARMS:
                    rt,v=refrows[s][arm][q]
                    strict=vals[arm+'/strict']
                    assert rt==t and strict[0]==v[0] and abs(strict[1]-v[3])<1e-12
                each[str(s)]=vals
            nchecked+=len(cache)
            result.append([q,t,each])
    assert len(result)==2000 and len(set(t for _,t,_ in result))==1207
    save(D/'scores.json.gz',result)
    save(D/'score-receipt.json',dict(evaluated=nchecked,strict_checks=20000,results=sha(D/'scores.json.gz'),forecasts=sha(D/'forecast-complete.json')))
    print('graded',nchecked,flush=True)

if __name__=='__main__':
    if sys.argv[1]=='rank':forecast(list(map(int,sys.argv[2:])) or SEEDS)
    elif sys.argv[1]=='grade':grade()
    else:raise ValueError(sys.argv[1])

"""Evaluate only sealed predictions against an atomic partition and the official span scorer."""
from common45 import *
sys.path.insert(0,str(W/'graph_memory_round33/budget_loss'))
import data as src

def main(stage):
    receipt=read(D/f'{stage}-forecast.json')
    assert receipt['table']==sha(D/'table.json') and receipt['predict']==sha(D/'predict.py')
    for file,h in receipt['files'].items():assert sha(D/file)==h
    prior={r['q']:r for r in (signed(R42,'scores.json.gz') if stage=='mid' else signed(FIX,'outcomes.json.gz'))}
    prior_bit={r['q']:r for r in signed(R43,'outcomes.json.gz')} if stage=='mid' else {}
    ap=W/'graph_memory_round34/interval_witness/test-atoms.json.gz';gp=src.nm.OFF/'gold-spans.json.gz'
    partition=read(ap);gold=read(gp);out=[];checks=0
    for sh,source in enumerate(src.sources('test')):
        pp=read(D/f'{stage}-{sh}.json.gz')
        avail={q:set(ids) for q,t,n,ids in signed(R42,f'test-{sh}.json.gz')} if stage=='mid' else {
            q:set(v[2]) for q,v in signed(FIX,f'packets-{sh}.json.gz').items()}
        for raw in read(source):
            q,t=raw['q'],raw['t'];old=prior[q]
            st,fired,entries=pp[q];assert st==old['t']==t and (stage=='mid' or fired==old['fired'])
            spans=[(b-a,set(ids)) for _,a,b,ids in partition[q]];size=sum(w for w,_ in spans)
            amt=sum(w for w,ids in spans if ids&avail[q]);assert old['eligible']==(amt==size)
            truth=tuple(src.nm.pilot.SourceSpan.model_validate(x) for x in gold[q])
            candidates=tuple(src.nm.pilot.RankedNodeRecord.model_validate(n) for n in raw['rr'])
            vals={};cache={}
            for s in SEEDS:
                scores={}
                for arm in ('rich','bit','table','native'):
                    seq=tuple(entries[str(s)][arm]) if fired else ()
                    if seq not in cache:
                        ids=set(seq);assert len(ids)==len(seq) and ids<=avail[q]
                        packet=tuple(candidates[i] for i in seq);cost=sum(n.token_count for n in packet)
                        res=src.nm.pilot.span_metrics_under_token_budget(packet,truth,2048)
                        cover=sum(w for w,idx in spans if idx&ids)
                        assert cost<=2048 and bool(res.full_support)==(cover==size) and abs(res.coverage-cover/size)<1e-12
                        cache[seq]=[int(cover==size),cover/size,cost]
                    scores[arm]=cache[seq]
                if fired:
                    prior_scores=old['arms'][str(s)]
                    assert scores['rich']==prior_scores['hgb/rich' if stage=='mid' else 'rich']
                    assert scores['native']==prior_scores['native_wo']
                    if stage=='mid':assert scores['bit']==prior_bit[q]['arms'][str(s)]['value_bit']
                vals[str(s)]=scores
            checks+=len(cache)
            out.append(dict(q=q,t=t,fired=fired,pilot=old['pilot'],eligible=(amt==size),arms=vals))
    assert len(out)==2000
    outpath=D/f'{stage}-outcomes.json.gz';save(outpath,out)
    save(D/f'{stage}-grade.json',dict(forecast=sha(D/f'{stage}-forecast.json'),unique_checks=checks,
        outcomes=sha(outpath),gold=sha(gp),atoms=sha(ap),grade=sha(D/'grade.py')))

if __name__=='__main__':main(sys.argv[1])

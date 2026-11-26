"""Independent span, token, denominator, signed baseline and paired-count verification."""
from common45 import *

def main():
    m=read(D/'manifest.json')['files']
    assert m=={p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name!='manifest.json'}
    check_registration();audit=read(D/'audit.json')
    assert audit['table']==sha(D/'table.json') and audit['mid']==sha(D/'mid-forecast.json') and audit['checked_lists']==10000
    atoms=read(W/'graph_memory_round34/interval_witness/test-atoms.json.gz')
    total=0
    for stage in ('mid','trigger'):
        rec=read(D/f'{stage}-forecast.json');graded=read(D/f'{stage}-grade.json')
        assert rec['table']==sha(D/'table.json') and graded['forecast']==sha(D/f'{stage}-forecast.json')
        assert graded['outcomes']==sha(D/f'{stage}-outcomes.json.gz')
        rows={r['q']:r for r in read(D/f'{stage}-outcomes.json.gz')}
        for sh in range(8):
            resources=read(W/f'graph_memory_round19/trained_rank/forecasts-main-{sh}.json.gz')
            file=D/f'{stage}-{sh}.json.gz';assert sha(file)==rec['files'][file.name]
            packs=read(file)
            hist=signed(R43,f'packets-{sh}.json.gz') if stage=='mid' else signed(FIX,f'packets-{sh}.json.gz')
            for row in resources:
                q=row['q'];lookup=[n['token_count'] for n in row['rr']]
                t,fired,pred=packs[q];out=rows[q];assert t==out['t'] and fired==out['fired']
                spans=[(b-a,set(ids)) for _,a,b,ids in atoms[q]];size=sum(k for k,_ in spans)
                for s in SEEDS:
                    ss=str(s)
                    for arm in ('rich','table','bit','native'):
                        seq=pred[ss][arm] if fired else []
                        if fired and arm=='rich':assert seq==hist[q][1 if stage=='mid' else 3][ss]['rich']
                        if fired and arm=='bit' and stage=='mid':assert seq==hist[q][1][ss]['value_bit']
                        chosen=set(seq);assert len(seq)==len(chosen)
                        cover=sum(k for k,ids in spans if not chosen.isdisjoint(ids));cost=sum(lookup[i] for i in seq)
                        assert [int(cover==size),cover/size,cost]==out['arms'][ss][arm] and cost<=2048
                        total+=1
        result=read(D/f'{stage}-results.json')
        assert result['grade']==sha(D/f'{stage}-grade.json') and result['bootstrap']==10000
        for group,v in result['groups'].items():
            selected=[r for r in rows.values() if group=='all' or (group=='nonpilot' and not r['pilot']) or
                (group=='fired' and r['fired']) or (group=='primary' and r['fired'] and r['eligible'] and not r['pilot'])]
            assert v['questions']==len(selected) and v['trajectories']==len({r['t'] for r in selected})
            for contrast in v['comparisons']:
                dif=[r['arms'][str(s)][contrast['left']][0]-r['arms'][str(s)][contrast['right']][0] for r in selected for s in SEEDS]
                assert contrast['wins']==dif.count(1) and contrast['losses']==dif.count(-1)
                assert abs(contrast['delta'][0]-sum(dif)/len(dif))<1e-15
    assert total==80000;print('verified',total,'packets over both timings')

if __name__=='__main__':main()

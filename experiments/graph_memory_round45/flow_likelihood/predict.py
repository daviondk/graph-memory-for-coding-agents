"""Use the frozen table and models to forecast, with no evaluation imports."""
from common45 import *
from likelihood import axes
import models42 as m
import numpy as np

def weights():
    table=read(D/'table.json')
    assert table['registration']==sha(D/'registration.json') and table['fit']==sha(D/'likelihood.py')
    a=signed(R42,'models.json')['models']['rich']['hgb']
    b=signed(R43,'weights.json')['models']
    assert a==b['rich']
    return a,b['value_bit'],np.array(table['log_ratio'])

def score(rows,meta,edge,sem_by,models,prior):
    rich,bit,table=models;c=np.rint(np.expm1(meta[:,1])).astype(int)
    out={q:[t,True,{}] for q,t,n,ix in rows}
    for s in SEEDS:
        sem=sem_by[s]
        rank,strata,bits=axes(sem,meta,edge)
        x=np.column_stack([sem,meta])
        rich_score=m.portable(rich,x)
        by={'rich':rich_score,'table':rich_score+table[strata,bits],
            'bit':m.portable(bit,np.column_stack([x,edge[:,4:6]>0]))}
        at=0
        for q,t,n,ids in rows:
            sl=slice(at,at+n);at+=n;ix=np.asarray(ids)
            packs={}
            for arm,value in by.items():
                order=np.lexsort((rank[sl],-value[sl]))
                packs[arm]=ix[firstfit(order,c[sl])].tolist()
            ref=prior[q][str(s)];assert packs['rich']==ref['rich']
            if 'bit' in ref:assert packs['bit']==ref['bit']
            packs['native']=ref['native']
            assert len(set(packs['native']))==len(packs['native']) and set(packs['native'])<=set(ids)
            out[q][2][str(s)]=packs
        assert at==len(c)
    return out

def freeze(stage,files):
    final=dict(table=sha(D/'table.json'),registration=sha(D/'registration.json'),predict=sha(D/'predict.py'),
               files={p.name:sha(p) for p in files})
    if stage=='trigger':final['code']=sha(D/'fixed.py')
    save(D/f'{stage}-forecast.json',final)

def midpoint():
    check_registration();models=weights()
    natives={q:p for q,t,p in signed(NATIVE,'forecast-packets.json.gz')}
    inv=read(R42/'manifest.json')['files'];files=[]
    for sh in range(8):
        fp=R42/f'test-{sh}.npz';rows=signed(R42,f'test-{sh}.json.gz')
        hist=signed(R43,f'packets-{sh}.json.gz')
        refs={q:{str(s):dict(rich=hist[q][1][str(s)]['rich'],bit=hist[q][1][str(s)]['value_bit'],
                native=natives[q][f'{s}/wo_chunk_adjacency'][1]) for s in SEEDS} for q,t,n,ids in rows}
        assert sha(fp)==inv[fp.name]
        with np.load(fp) as z:
            p=score(rows,z['meta'],z['edge'],{s:z[f'sem{s}'] for s in SEEDS},models,refs)
        file=D/f'mid-{sh}.json.gz';save(file,p);files.append(file)
    freeze('mid',files);print('mid sealed',flush=True)

if __name__=='__main__':midpoint()

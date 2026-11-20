"""Compact table values for checking the Russian report against paired records."""
from run import D,load
v=load(D/'results.json')
for k,b in v['overall'].items():
    print(k,b['n'],b['projects'])
    print(' | '.join(f"{a}={'/'.join(map(str,x['hits']))} {x['mrr']:.4f}" for a,x in b['items'].items()))
    for key in b['diff']:
        if key.split('-')[0]!='full':continue
        x=b['diff'][key]
        fmt=lambda v:round(v*100,2)
        print(key,*(fmt(x[s][0]) for s in ('delta','lo','hi','macro')),x['wins'],x['losses'])
print('Hard fresh', [(a,v['fresh_encoder_hard']['items'][a]['hits']) for a in ['full','r4','unix','semlith']])
print('Hard using author crop', [(a,v['author_encoder_hard']['items'][a]['hits']) for a in ['full','r4','unix']])
print('Holm',v['primary_p_holm'])
print('native',v['native_python_mean_returned'],v['native_python_zero_returned'])

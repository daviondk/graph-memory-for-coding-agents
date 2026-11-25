"""Verify the equal-spending subexperiment against sealed upstream outputs."""
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
from statistics import mean
import numpy as np
D=Path(__file__).resolve().parent
spec=spec_from_file_location('r23_independent_verification',D/'verify.py');baseline=module_from_spec(spec);spec.loader.exec_module(baseline)
read,digest,groups,coverage=baseline.read,baseline.digest,baseline.groups,baseline.coverage
def check(stage):
    fp=D/f'{stage}-equal-spend-forecasts.json.gz';rp=D/f'{stage}-equal-spend-outcomes.json.gz';s=read(D/f'{stage}-equal-spend-seal.json')
    stats=read(D/f'{stage}-equal-spend-results.json')
    assert s['predictions']==digest(fp) and s['main_seal']==digest(D/f'{stage}-seal.json') and stats['per_query']==digest(rp)
    official=D.parents[1]/('graph_memory_round19/write_transfer' if stage=='dev' else 'graph_memory_round18/isetrace_official')
    gold=read(official/'gold-spans.json.gz');o={r['q']:r for r in read(rp)};k=('full','coverage','density','f1','tokens');data={}
    for rec in read(fp):
        q=rec['q'];parent=read(D/'forecasts'/stage/f'{q[6:]}.json.gz');ad=rec['ad'];assert parent['ad']==ad
        arm=parent['picks']['verbatim_core'];assert rec['picks']['verbatim_core']==arm and rec['cap']==arm['tokens']
        truth=groups([(sp['event_id'],sp['json_pointer'],sp['char_start'],sp['char_end']) for sp in gold[q]])
        for a,pick in rec['picks'].items():
            assert 0<=pick['tokens']<=rec['cap']<=2048
            pred=groups([(*ad[e],l,h) for e,l,h in pick['spans']]);values=coverage(truth,pred)
            y=o[q]['scores'][a];z=[*values[:4],pick['tokens']];assert np.allclose(z,[y[f] for f in k],atol=1e-12,rtol=0)
            data[q,a]=z
    for a,r in stats['pairs_against_verbatim'].items():
        x=np.asarray([np.asarray(data[q,a])-data[q,'verbatim_core'] for q in sorted(o)]);rng=np.random.default_rng(13)
        arr=np.vstack([x[rng.integers(len(o),size=(100,len(o)))].mean(axis=1) for _ in range(100)])
        ci=np.quantile(arr,[.025,.975],axis=0)
        assert np.allclose(x.mean(axis=0),[r['diff'][f]['estimate'] for f in k],atol=1e-12,rtol=0)
        assert np.allclose(ci.T,[r['diff'][f]['ci95'] for f in k],atol=1e-12,rtol=0)
    print(stage,len(o),'equal-spending outcomes verified')
if __name__=='__main__':
    import sys
    for s in (sys.argv[1:] or ['dev','test']):check(s)

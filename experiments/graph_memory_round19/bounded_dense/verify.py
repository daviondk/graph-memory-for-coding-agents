"""Recalculate the released study from coordinates, using the standard library alone."""
import importlib.util
from pathlib import Path
from statistics import mean
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ise_arithmetic', ROOT.parent/'trained_rank/verify.py')
arithmetic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arithmetic)
get, sha, union, compute = arithmetic.get, arithmetic.sha, arithmetic.union, arithmetic.compute

def main():
    manifest = get(ROOT/'MANIFEST_SHA256.json')
    assert all(sha(ROOT/n)==v for n,v in manifest.items())
    seal = get(ROOT/'forecast-seal.json')
    plan = get(ROOT/'reader-plan.json')
    assert seal['plan']==sha(ROOT/'reader-plan.json')
    assert all(sha(ROOT/n)==v for n,v in (seal['forecasts']|plan['files']).items())
    out = {(r['stage'],r['q'],r['writer'],r['reader']):r for r in get(ROOT/'outcomes.json.gz')}
    summary = get(ROOT/'results.json')
    groups = defaultdict(list)
    rows = set()
    for stage in ('test','dev'):
        goldpath = (arithmetic.R18/'isetrace_official/gold-spans.json.gz' if stage=='test'
                    else ROOT.parent/'write_transfer/gold-spans.json.gz')
        assert sha(goldpath)==summary[stage]['gold_sha256']
        truth = {q:union(spans) for q,spans in get(goldpath).items()}
        seen = set()
        for i in range(8):
            for traj in get(ROOT/f'forecasts-{stage}-{i}.json.gz'):
                nodes = {}
                for j,(e,p,lo,hi,c,nb) in traj['b'].items():
                    assert hi>lo and nb>0 and c>0
                    span=dict(event_id=e,json_pointer=p,char_start=lo,char_end=hi)
                    nodes[int(j)]=dict(source_spans=[span],token_count=c)
                for writer, data in traj['arms'].items():
                    keep = data['k']; reachable = set(keep)
                    assert len(keep)==len(reachable) and sum(nodes[j]['token_count'] for j in keep)<=8192
                    for q,methods in data['per'].items():
                        seen.add(q)
                        ceiling=compute(truth[q],[nodes[j] for j in keep])
                        for reader,selected in methods.items():
                            assert len(selected)==len(set(selected)) and set(selected)<=reachable
                            key=(stage,q,writer,reader); assert key not in rows;rows.add(key)
                            r=out[key]
                            metric=compute(truth[q],[nodes[j] for j in selected])
                            assert metric['tokens']<=2048 and r['t']==traj['t']
                            assert all(abs(r[m]-v)<1e-12 for m,v in metric.items())
                            assert r['write_fs']==ceiling['full_support'] and abs(r['write_coverage']-ceiling['coverage'])<1e-12
                            groups[stage,writer+'/'+reader].append(r)
        assert seen==set(truth)
    assert rows==set(out) and len(rows)==23220
    for (stage,key),recs in groups.items():
        a=summary[stage]['metrics'][key]
        assert len(recs)==a['n'] and sum(r['full_support'] for r in recs)==a['hits']
        for m in ('tokens','full_support','coverage','density','f1','nodes','write_fs','write_coverage'):
            assert abs(mean(r[m] for r in recs)-a[m])<1e-12
    print('Verified',len(manifest),'file hashes,',len(rows),'query-level readings and',len(groups),'cohort averages.')
if __name__=='__main__':main()


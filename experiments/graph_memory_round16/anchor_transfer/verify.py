"""Offline recheck of prediction seals and two native metrics from intersection of line identities."""
import collections
import json
from statistics import median
from cohort import BENCH, CACHE, ROOT, load, sha

def lines(regions):
    return {(p,n) for p,s,e in regions for n in range(s,e+1)}

def main():
    for n in ("cohort.lock.json","inputs.lock.json","predictions.lock.json"):
        contents=load(ROOT/n)
        for name,h in contents.get('files',contents).items():
            assert sha((ROOT/name).read_bytes())==h,(name,n)
    tasks=load(ROOT/'cohort.json')['tasks']
    native={r['instance_id']:r for r in (json.loads(l) for l in BENCH.read_bytes().splitlines()) if r['instance_id'] in tasks}
    forecasts=load(ROOT/'forecast.json.gz')
    scores=load(ROOT/'scores.json.gz')
    assert len(scores)==len(forecasts)==4*len(tasks)
    identity=lambda r:(r['id'],r['source'],r['window'])
    refs={identity(r):r for r in scores}
    checks=0
    precision_values=[]
    core_sizes=[]
    for iid,g in native.items():
        core_sizes.append(len(lines([(v['path'],v['start'],v['end']) for v in g['ground_truth']['read_core_regions']])))
    for row in forecasts:
        core=lines([(v['path'],v['start'],v['end']) for v in native[row['id']]['ground_truth']['read_core_regions']])
        for arm,value in row['arms'].items():
            pred=lines(value['regions']); n=len(pred & core)
            s=refs[identity(row)]['scores'][arm]
            assert abs(s['precision']-(n/len(pred) if pred else 0))<1e-12
            assert abs(s['recall']-(n/len(core) if core else 0))<1e-12
            checks+=2
            if row['window']==3 and pred: precision_values.append(s['precision'])
    for row in load(ROOT/'observations.json.gz'):
        original=CACHE/'trajectories'/row['source']/(row['instance_id']+'.json')
        assert sha(original.read_bytes())==row['trajectory_sha256']
    n=len(precision_values)
    print("metric values verified:",checks,"median core lines:",median(core_sizes),"binary among nonempty three-event outputs:",sum(x in (0,1) for x in precision_values),"/",n)
if __name__=='__main__':
    main()

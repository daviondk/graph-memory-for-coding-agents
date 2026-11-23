"""Read labels only after prediction seal and use the public SWE-Explore scorer."""
import collections
import json
import random
import sys
from statistics import mean, median

from cohort import BENCH, MODELS, OFFICIAL, ROOT, WORK, load, save, sha

METRICS=["precision","recall","f1_score","ndcg_at_100"]
ARMS=["first","recent","repeated","graph","split"]
def aggregate(rows):
    return {a:{m:mean(r["scores"][a][m] for r in rows) for m in METRICS} for a in ARMS}

def contrast(rows,a,b):
    issues=collections.defaultdict(list)
    for r in rows:
        delta=r["scores"][a]["precision"]-r["scores"][b]["precision"]
        issues[r["repo"],r["id"]].append(delta)
    byrepo=collections.defaultdict(list)
    for (repo, _),v in issues.items():byrepo[repo].append(mean(v))
    vals=[v for values in byrepo.values() for v in values]
    rng=random.Random(1630)
    sims=[]
    for _ in range(5000):
        sample=[v for repo in rng.choices(list(byrepo),k=len(byrepo)) for v in byrepo[repo]]
        sims.append(sum(sample)/len(sample))
    sims.sort()
    return {"n":len(vals),"delta":mean(vals),"repo_cluster_ci":[sims[124],sims[4874]],"wins":sum(v>1e-12 for v in vals),"losses":sum(v< -1e-12 for v in vals)}

def main():
    for n,h in load(ROOT/"predictions.lock.json")["files"].items(): assert sha((ROOT/n).read_bytes())==h
    source=load(WORK/"graph_memory_round15/external_scoring/native-source.json")
    assert sha((OFFICIAL/"swe_eval.py").read_bytes())==source["swe_eval.py"]["sha256"]
    assert sha(BENCH.read_bytes())==load(ROOT/"cohort.json")["sha_external"]
    sys.path.insert(0,str(OFFICIAL))
    from swe_eval import ExploreEvaluator
    ev=ExploreEvaluator(BENCH)
    forecasts=load(ROOT/"forecast.json.gz")
    scores=[]
    for model in MODELS:
        for window in (3,6):
            cohort={r['id']:r for r in forecasts if r['source']==model and r['window']==window}
            results={a:ev.evaluate(lambda q,i:cohort[i]['arms'][a]['regions'],list(cohort),METRICS) for a in ARMS}
            for i,r in cohort.items():
                scores.append({**{k:r[k] for k in ('id','repo','window','source','views')},
                               'lines':{a:r['arms'][a]['lines'] for a in ARMS},
                               'scores':{a:results[a][i] for a in ARMS}})
    save('scores.json.gz',scores)
    summary={}
    for w in (3,6):
        for source in ['combined',*MODELS]:
            rows=[r for r in scores if r['window']==w and (source=='combined' or r['source']==source)]
            summary[f'{w}/{source}']={'rows':len(rows),'nonempty':sum(bool(r['views']) for r in rows),'means':aggregate(rows),
                'lines':{a:sum(r['lines'][a] for r in rows) for a in ARMS},
                'contrasts':{a+'-'+b:contrast(rows,a,b) for a,b in [('first','recent'),('split','first'),('graph','recent')]}}
    selected=load(ROOT/'cohort.json')['tasks']
    issues=[ev.bench_data_dict[i] for i in selected]
    universe={'dataset':dict(collections.Counter(r.get('dataset') for r in issues)),
        'optional_models': sorted({m for r in issues for m in r['ground_truth'].get('read_optional_regions_map',{})}),
        'unbounded':sum(x['start']<1 or x['end']<1 for r in issues for x in r['ground_truth']['read_core_regions']),
        'scorer_sha':sha((OFFICIAL/'swe_eval.py').read_bytes())}
    assert universe['unbounded']==0
    save('results.json',{'summary':summary,'benchmark':universe})
    print(universe)
    for name,result in summary.items():
        print(name,result['rows'],result['nonempty'],{a:[round(v,4) for v in r.values()] for a,r in result['means'].items()},result['contrasts']['first-recent'],result['contrasts']['split-first'])
if __name__=="__main__":
    main()

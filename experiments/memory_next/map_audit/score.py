"""Export the authors' recorded results, then score the frozen strata."""
from assign import ROOT,store,digest,pq
from verify import data,aggregate,verify
for n,h in data('lock.json').items():
    assert digest(ROOT/n)==h
rows=pq.read_table(ROOT/'data_runs_train.parquet',columns=['target_id','artifact_condition','resolved','non_empty_patch']).to_pylist()
store('outcomes.json',rows)
store('results.json',aggregate(data('strata.json'),rows))
store('artifact-hashes.json',{n.name:digest(n) for n in ROOT.iterdir() if n.is_file() and (n.name.startswith(('data_','manifests_','tables_')) or n.name in ['LICENSE','README.md'])})
verify()
print(data('results.json'))


"""Record public commit identities, effective finetuning config and split integrity."""
from pathlib import Path
from collections import Counter
import importlib.metadata as md, json, subprocess
from prepare import ROOT,RUN,R18,pilot,load,put,OFF
def run():
    s=load(ROOT/'split.json.gz')
    ts={k:{r['t'] for r in v} for k,v in s.items()};qs={k:{r['q'] for r in v} for k,v in s.items()}
    assert all(not(ts[a]&ts[b] or qs[a]&qs[b]) for a,b in [('train','dev'),('train','test'),('dev','test')])
    assert len(set.union(*qs.values()))==sum(map(len,qs.values()))
    assert [r['q'] for r in s['test']]==[r['query_id'] for r in load(OFF/'cohort.json')]
    sources=['configs/profile/full.yaml','configs/dataset/isetrace.yaml','configs/stage/dense_ft.yaml','configs/method/dense_ft_rgcn_graph_retriever.yaml',
        'graph_memory/experiment/config.py','graph_memory/datasets/isetrace/benchmark_adapter.py','graph_memory/datasets/isetrace/training.py',
        'graph_memory/models/dense_finetune/data.py','graph_memory/models/dense_finetune/training.py','graph_memory/training_pairs/builder.py',
        'graph_memory/training_pairs/config.py','graph_memory/stages/models.py','graph_memory/stages/pairs.py','graph_memory/evaluation/span_metrics.py']
    p=pilot.UPSTREAM;weights=pilot.CACHE.parent/'e5-base-v2';iv=load(R18/'isetrace_e5/inventory.json')
    for f in iv['weights']:assert pilot.sha(weights/f['path'])==f['sha256']
    put(ROOT/'source-audit.json',dict(commit=pilot.CODE,remote=subprocess.check_output(['git','-C',str(p),'remote','get-url','origin']).decode().strip(),
        upstream_files={n:pilot.sha(p/n) for n in sources},base_weights_revision='f52bf8ec8c7124536f0efb74aca902b2995e5bcd',
        base_weights={f['path']:f['sha256'] for f in iv['weights']},dependencies={n:md.version(n) for n in ('torch','sentence-transformers','transformers','tokenizers','numpy','pydantic')},
        raw_locks={n:pilot.sha(OFF/n) for n in ['source-lock.json','cohort.json','split-verification.json']},query_counts={k:len(v) for k,v in qs.items()},
        represented_trajectories={k:len(v) for k,v in ts.items()},disjoint_query_true=True,disjoint_trajectory_true=True,test_order_matches_frozen=True,available_dev_queries=580,available_dev_trajectories=352,
        profile_dev_count=500,optimizer_seed=13,data_split_seed=13,source_coordinate_overlap='graph_memory.trajectories.source_spans_overlap',labels_in_dump='train+dev only'))
if __name__=='__main__':run()

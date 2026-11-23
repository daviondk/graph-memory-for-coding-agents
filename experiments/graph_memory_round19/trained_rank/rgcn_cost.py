"""Measure the reusable PU subset of a potential residual R-GCN feature build; no new GPU use."""
from collections import Counter
from pathlib import Path
import hashlib,sqlite3,time
from prepare import ROOT,RUN,R18,load,put,pilot
from project import CACHE
def run():
    started=time.monotonic()
    ss=set();counts={};base={k for (k,) in sqlite3.connect((CACHE/'vectors.sqlite3').resolve().as_uri()+'?mode=ro',uri=True).execute('select k from corpus')}
    for split in ['train','dev']:
        local=set();nodes=qs=traj=0
        for p in sorted((RUN/'projection'/split).glob('*.json.gz')):
            r=load(p);traj+=1;nodes+=len(r['pool']);qs+=len(r['qs'])
            for c in r['pool']:local.add(hashlib.sha256(('passage: '+c['text']).encode()).digest())
            for q in r['qs']:local.add(hashlib.sha256(('query: '+q['text']).encode()).digest())
        ss|=local;counts[split]=dict(trajectories=traj,queries=qs,pu_occurrences=nodes,exact_unique_strings=len(local))
    need=len(ss-base);rate=load(R18/'isetrace_e5/cost-fp32.json')['seconds']/len(base)
    put(ROOT/'rgcn-cost.json',dict(pools=counts,unique_train_dev=len(ss),also_present_in_test=len(ss&base),net_new_pu_plus_query_strings=need,
        empirical_test_seconds_per_string=rate,reference_estimate_subset_minutes=need*rate/60,
        caveat='PU/query projection only; native feature formatting, non-PU nodes and runtime of graph minibatches are additional or may use different texts. Indicative scenario, not a runtime bound.',
        native_config=dict(hidden=256,layers=3,relations=14,epochs=15,batch_graphs=128,seed=13),scan_cpu_s=time.monotonic()-started))
if __name__=='__main__':run()

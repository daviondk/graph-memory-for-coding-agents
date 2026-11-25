"""Trajectory-cluster uncertainty within the two declared natural evidence groups."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from setup_graph import ROOT,R18,load,put,pilot
from evaluate import compare
def lock():put(HERE/'strata-plan.json',dict(source=pilot.sha(HERE/'strata.py'),definition=pilot.sha(HERE/'STRATA_RU.md'),parent=pilot.sha(HERE/'protocol-lock.json')))
def run():
    assert load(HERE/'strata-plan.json')['source']==pilot.sha(HERE/'strata.py')
    gt=load(R18/'isetrace_official/gold-spans.json.gz');A=load(ROOT/'outcomes.json.gz');B=load(HERE/'outcomes.json.gz')
    groups={'single':[q for q,g in gt.items() if len({s['event_id'] for s in g})==1],'multiple':[q for q,g in gt.items() if len({s['event_id'] for s in g})>1]}
    assert sum(map(len,groups.values()))==len(gt)
    arms={'rgcn':{r['q']:r for r in A if r['method']=='rgcn' and r['arm']=='prefix'},'seed':{r['q']:r for r in A if r['method']=='seed' and r['arm']=='prefix'}}
    arms.update({m:{r['q']:r for r in B if r['method']==m} for m in ['native','random','empty']})
    res={}
    for name,qs in groups.items():
        rr={k:{q:arm[q] for q in qs} for k,arm in arms.items()};sums={k:int(sum(r['full_support'] for r in grp.values())) for k,grp in rr.items()}
        contrasts={a+'-'+b:compare(rr[a],rr[b]) for a,b in [('rgcn','seed'),('native','random'),('native','empty')]} if qs else {}
        res[name]=dict(n=len(qs),trajectories=len({rr['rgcn'][q]['t'] for q in qs}),fs_hits=sums,contrasts=contrasts)
    put(HERE/'strata-results.json',res)
if __name__=='__main__':{'lock':lock,'run':run}[sys.argv[1]]()


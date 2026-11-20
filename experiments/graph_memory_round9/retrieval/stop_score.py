"""Assess paired budget/quality tradeoff after the main and companion seals."""
from collections import defaultdict
import json
import numpy as np
from source import ROOT,load_json,write_json,h
from score import metric,canon,compare
def main():
    seal=load_json(ROOT/'stop_seal.json')
    assert all(h((ROOT/f).read_bytes())==sha for f,sha in seal.items())
    gold={t:set(s) for t,s,_ in load_json(ROOT/'judgments.json')}
    sample=load_json(ROOT/'sample.json')['selected']
    details={};oracle={}
    for row in sample:
        t=row['issue'];g={canon(s) for s in gold[t]}
        if not g:continue
        s=load_json(ROOT/'stop_predictions'/(t+'.json'))['policies']
        p=load_json(ROOT/'predictions'/(t+'.json'));dense=p['ranks']['dense']
        obs={dst for src,m,dst in p['stored_edges'] if dst not in dense[:10]}
        oracle[t]={'gold_outside_top10':len(g-{canon(x) for x in dense[:10]}),'reachable_gold_outsiders':sorted(g&{canon(x) for x in obs}),'witness_eligible':len(obs)}
        vals={}
        for m,rec in s.items():
            rank=[canon(x) for x in rec['rank']]
            z=metric([k for k,v in enumerate(rank,1) if v in g],len(g))
            z.update(seed_reads=rec['reads'],seed_tokens=rec['tokens'],seed_bytes=rec['bytes'],extra_reads=int(rec['fresh'] is not None),all_reads=rec['reads']+int(rec['fresh'] is not None))
            vals[m]=z
        details[t]={'band':row['band'],'methods':vals}
    ids=list(details);methods=['fixed6','early','early3'];keys=details[ids[0]]['methods']['fixed6']
    groups=[[i for i,t in enumerate(ids) if details[t]['band']==b] for b in sorted({d['band'] for d in details.values()})]
    ix=np.concatenate([np.random.default_rng(91108+i).choice(g,size=(10000,len(g)),replace=True) for i,g in enumerate(groups)],axis=1)
    means={m:{v:float(np.mean([details[t]['methods'][m][v] for t in ids])) for v in keys} for m in methods}
    contrast={a+'-'+b:{v:compare([details[t]['methods'][a][v]-details[t]['methods'][b][v] for t in ids],ix) for v in keys} for a,b in [('early3','fixed6'),('early','fixed6'),('early3','early')]}
    write_json(ROOT/'stop_results.json',dict(means=means,contrasts=contrast,details=details,oracle_after_seal=oracle))
    for m in methods:print(m,*(round(means[m][k],3) for k in ['acc10','recall10','seed_reads','seed_tokens','extra_reads']))
if __name__=='__main__':main()

"""Post-lock official literal scoring and paired analyses, with a second typed-field outcome."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import random
from collections import Counter,defaultdict
from statistics import mean,median
ROOT=Path(__file__).resolve().parent
ARMS=['author_index','raw_tail','shuffle','round_robin','recent','frequency','author_grouped','witness_lines','witness_grouped']
BUDGETS=['natural','1024','4096']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def readgz(n):
    with gzip.open(ROOT/n,'rt',encoding='utf8') as f:
        for line in f:yield json.loads(line)
def qtile(arr,p):
    k=(len(arr)-1)*p
    i=int(k)
    return arr[i]+(arr[min(i+1,len(arr)-1)]-arr[i])*(k-i)
def ci(by_grp):
    totals=[(sum(ds),len(ds)) for ds in by_grp.values()]
    draws=[]
    rng=random.Random(20261117)
    for _ in range(10000):
        sample=rng.choices(totals,k=len(totals))
        draws.append(sum(d for d,n in sample)/sum(n for d,n in sample))
    draws.sort()
    return [qtile(draws,.025),qtile(draws,.975)]
def methods(rr):
    return {'n':len(rr),'macro_recall':mean(r['recall'] for r in rr),'micro_recall':sum(r['hits'] for r in rr)/sum(r['total'] for r in rr),'macro_exact_typed':mean(r['typed_recall'] for r in rr) if rr[0]['arm']!='raw_tail' else None,
            'mean_chars':mean(r['chars'] for r in rr),'mean_utf8_bytes':mean(r['bytes'] for r in rr),'mean_items':mean(r['items'] for r in rr),'all_hits':sum(r['hits'] for r in rr)}
def score():
    lock=load('prediction_lock.json')
    for n,h in lock['inputs'].items():assert digest(ROOT/n)==h
    assert lock['predictions_sha256']==digest(ROOT/'predictions.jsonl.gz')
    gold=list(readgz('gold.jsonl.gz'))
    assert len(gold)==lock['n_cases']
    rows=[];types=defaultdict(Counter);omitted=set();seen=set()
    hist_hash={}
    for row in readgz('histories.jsonl.gz'):
        hist_hash[row['i']]=hashlib.sha256(json.dumps(row['H'],ensure_ascii=False).encode()).hexdigest()
    for p in readgz('predictions.jsonl.gz'):
        g=gold[p['i']];atoms=g['atoms'];S=p['S']
        assert len(atoms)==g['n_atoms'] and len(S)<=p['cap']
        identity=(p['i'],p['budget'],p['arm']);assert identity not in seen
        seen.add(identity)
        if not atoms:omitted.add(p['i']);continue
        exact=set(map(tuple,p['items']))
        literal=[a['value'] in S for a in atoms]
        typed=[(a['kind'],a['value']) in exact for a in atoms]
        for a,y,t in zip(atoms,literal,typed):
            sub=types[p['budget'],p['arm'],a['kind']]
            sub.update({'count':1,'hits':int(y),'typed':int(t)})
        rows.append({'i':p['i'],'sample_id':g['sample_id'],'session':g['sess'],'client':g['client'],'history_sha256':hist_hash[p['i']],'budget':p['budget'],'arm':p['arm'],'cap':p['cap'],'chars':len(S),'bytes':len(S.encode()),'items':len(p['items']),'hits':sum(literal),'total':len(atoms),'typed_hits':sum(typed),'recall':mean(literal),'typed_recall':mean(typed)})
    assert len(seen)==len(gold)*len(BUDGETS)*len(ARMS)
    with (ROOT/'casewise.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    index={(r['budget'],r['arm'],r['i']):r for r in rows}
    results={'records':len(gold),'gold_atoms':sum(g['n_atoms'] for g in gold),'unique_sessions':len({g['sess'] for g in gold}),'unique_histories':len(set(hist_hash.values())),'excluded_zero_atom':sorted(omitted),'budgets':{}}
    for b in BUDGETS:
        arms={a:methods([r for r in rows if r['budget']==b and r['arm']==a]) for a in ARMS}
        comp={}
        for a in ARMS:
            aa=[r for r in rows if r['budget']==b and r['arm']==a]
            vals=[];ss=defaultdict(list)
            for r in aa:
                delta=r['recall']-index[b,'author_index',r['i']]['recall']
                ss[r['session']].append(delta)
                vals.append(delta)
            comp[a]={'delta_vs_author':mean(vals),'wins':sum(x>0 for x in vals),'losses':sum(x<0 for x in vals),'ties':vals.count(0),'cluster_ci95':ci(ss) if a=='witness_grouped' else None}
        byc={}
        for client in sorted({r['client'] for r in rows}):
            byc[client]={a:methods([r for r in rows if r['budget']==b and r['arm']==a and r['client']==client]) for a in ['author_index','witness_grouped','frequency','author_grouped']}
        results['budgets'][b]={'methods':arms,'comparisons':comp,'by_client':byc}
    results['by_type']={'|'.join(keys):dict(v) for keys,v in types.items()}
    return results
if __name__=='__main__':
    res=score()
    (ROOT/'results.json').write_text(json.dumps(res,indent=1,ensure_ascii=False),encoding='utf8')
    for b,r in res['budgets'].items():print(b,[(a,round(r['methods'][a]['macro_recall']*100,2)) for a in ARMS],r['comparisons']['witness_grouped'])


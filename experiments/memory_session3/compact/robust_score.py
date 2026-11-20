"""Exploratory pairwise robustness, including published temporal disorder and per-kind/agent breakouts."""
import csv
import json
from collections import Counter,defaultdict
from statistics import mean
from followup_score import check,csvsave,save
from score import ROOT,ci,readgz
from predict import author
from e3_score import PENDING_RE

def compare(rows,a,b):
    base={r['key']:r for r in rows if r['arm']==b and r['n']}
    av=[r for r in rows if r['arm']==a and r['n']]
    deltas=[(r['hits']-base[r['key']]['hits'])/r['n'] for r in av]
    groups=defaultdict(list)
    for r,x in zip(av,deltas):groups[r['i']].append(x)
    return {'macro':mean(r['hits']/r['n'] for r in av),'delta':mean(deltas),'ci':ci(groups),'wins':sum(d>0 for d in deltas),'losses':sum(d<0 for d in deltas),'ties':deltas.count(0),'micro':sum(r['hits'] for r in av)/sum(r['n'] for r in av)}
def further_e2():
    ys={int(k):v for k,v in json.loads((ROOT/'future_ground_truth.json').read_text(encoding='utf8')).items()}
    rows=[]
    for r in readgz('robust_e2.jsonl.gz'):
        i=r['i'];target=ys[i]
        rows.append(dict(i=i,key=i,arm=r['arm'],n=len(target),hits=sum(v in r['S'] for k,v in target)))
    with (ROOT/'token_casewise.csv').open(encoding='utf8') as f:
        for r in csv.DictReader(f):
            if r['endpoint']=='future':
                i=int(r['i'])
                rows.append(dict(i=i,key=i,arm=r['arm'],n=int(r['n']),hits=int(r['hits'])))
    csvsave('robust_future_casewise.csv',rows)
    arms=sorted({r['arm'] for r in rows})
    return {a:{b:compare(rows,a,b) for b in ['author_index','frequency','witness_grouped']} for a in arms}
def further_e3():
    outcomes={}
    with (ROOT/'source/chains.jsonl').open(encoding='utf8') as f:
        for i,line in enumerate(f):
            chain=json.loads(line)
            ks=[p['k'] for p in chain['per_k']]
            assert ks==sorted(set(ks)),(i,ks)
            for j,p in enumerate(chain['per_k']):
                outcomes[i,j]=p,chain['client']
    rows=[];kindstats=defaultdict(Counter);clients=defaultdict(list)
    for file in ['e3_predictions.jsonl.gz','robust_e3.jsonl.gz']:
        for r in readgz(file):
            if r['j']==0:continue
            key=r['i'],r['j']; g,cl=outcomes[key]; s=r['S'];a=r['arm']
            gold=[(k,v) for k,vs in g['atomsF'].items() for v in vs]
            pending_matches=list(PENDING_RE.finditer(s))
            ctx='\u0000'.join(s[max(0,m.start()-150):m.end()+150] for m in pending_matches)
            disorder=any(f.split('/')[-1] in ctx for f in g.get('done_files',[])) if pending_matches else False
            rec={'i':key[0],'j':key[1],'key':key,'arm':a,'client':cl,'n':len(gold),'hits':sum(v in s for k,v in gold),'tokens':r['used'],'disorder':int(disorder),'done_f':len(g.get('done_files',[]))}
            rows.append(rec)
            for k,v in gold:kindstats[a,k].update({'n':1,'hits':int(v in s)})
            if gold:clients[a,cl].append(rec['hits']/len(gold))
    csvsave('robust_e3_casewise.csv',rows)
    arms=sorted({r['arm'] for r in rows})
    return {'comparisons':{a:{b:compare(rows,a,b) for b in ['production','sidecar_fixed']} for a in arms},'temporal':{a:{'adverse_any_sum':sum(r['disorder'] for r in rows if r['arm']==a),'nonempty_done_files':sum(bool(r['done_f']) for r in rows if r['arm']==a),'all':sum(1 for r in rows if r['arm']==a)} for a in arms},'clients':{'|'.join(k):{'n':len(v),'mean':mean(v)} for k,v in clients.items()},'types':{'|'.join(k):v for k,v in kindstats.items()}}
def main():
    for t in ['e2','e3']:check(f'robust_{t}_lock.json')
    save('robust_results.json',{'future':further_e2(),'chains':further_e3()})
if __name__=='__main__':main()


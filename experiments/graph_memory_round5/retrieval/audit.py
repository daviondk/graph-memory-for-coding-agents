from common5 import *
from collections import Counter
def main():
    score=load(D/'rank_result.json')['by_query']['3'];neu=load(D/'neural_result.json')['by_query']
    for tag in ('rank','neural','budget','transfer'):
        l=load(D/(tag+('_decisions.json' if tag in ('rank','neural') else '_lock.json')))
        assert filehash(D/(tag+'_predictions.jsonl.gz'))==l['pred']
    l=load(D/'neural_devlock.json')
    assert l['sha']==filehash(D/'neural_weights.json')==filehash(D/'neural_preregistered_weights.json')
    assert l['inference']==filehash(D/'neural_rank.py')
    for arm,index in [('graph','graph'),('jaccard','jaccard'),('owner','owner')]:
        a=score['metrics'][arm]['micro']
        assert max(abs(x-y) for x,y in zip(a,load(R/'archive_results.json')['all']['metrics'][index]))<1e-12
    pregs=[score['contrasts']['adaptive-linear']['top1_signflip_p'],neu['3']['contrasts']['edge-direct']['top1_signflip_p']]
    ascending=sorted(range(2),key=pregs.__getitem__);holm=[0.,0.];running=0.
    for j,i in enumerate(ascending):
        running=max(running,min(1.,(2-j)*pregs[i]));holm[i]=running
    online=load(D/'online_lock.json');cns={}
    for lang,h in online['outputs'].items():
        p=D/('online_'+lang+'.jsonl.gz');assert filehash(p)==h
        bank=Counter();last={};small=100.;high=-1.;n=0
        for panel,j,repo,seed,t,*dep in rr(p):
            assert t==last.get(seed,-1)+1;last[seed]=t;n+=1
            for a,x in enumerate(dep):
                key=(repo,seed,a);bank[key]+=3-x;small=min(small,bank[key]);high=max(high,bank[key]);assert 0<=bank[key]<=12
        cns[lang]=dict(events=n,min_credit=small,max_credit=high,seeds=len(last))
    bundle={p.name:filehash(p) for p in D.iterdir() if p.is_file() and (p.suffix=='.py' or 'lock' in p.name or p.name.endswith(('.jsonl.gz','result.json','results.json'))) and not p.name.startswith('discarded')}
    dump('audit.json',dict(utc=now(),hashes=bundle,rank_p=pregs[0],rank_holm=holm[0],neural_p=pregs[1],neural_holm=holm[1],online=cns,old_graph_macro_match=True,dev_neural_graph_mismatches=0))
if __name__=='__main__':main()


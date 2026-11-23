"""Portable independent verification. Only Python standard library and this directory required."""
from pathlib import Path
from collections import Counter
import hashlib,gzip,json
D=Path(__file__).resolve().parent
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(n):
    b=(D/n).read_bytes();return json.loads(gzip.decompress(b) if n.endswith('.gz') else b)
def sortbag(pairs,r):return sorted(pairs,key=lambda p:(-pairs[p],-r[p]['last'],p))
def main():
    if (D/'MANIFEST_SHA256.json').exists():
        assert all(h(D/p)==sha for p,sha in load('MANIFEST_SHA256.json').items())
    for n,sha in load('forecast.lock.json').items():assert h(D/n)==sha,n
    seal=load('outcome.lock.json')
    assert h(D/'forecast.lock.json')==seal['forecast_lock'] and all(h(D/n)==s for n,s in seal['files'].items())
    ii=load('frontier_inputs.json.gz');pp=load('forecasts.json.gz');checks=load('causal_receipts.json.gz')
    evals=load('evaluation_rows.json.gz');s=load('results.json');labels=load('outcomes.json.gz');pairs=load('paired.json')
    total=0;linkn=0;ranking={}
    for panel,rows in ii.items():
        assert len(pp[panel])==len(rows)==len(checks[panel])==len(labels[panel])
        for r,model,rec in zip(rows,pp[panel],checks[panel]):
            assert r['id']==model['id']==rec['id']
            serial=json.dumps(r,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode()
            assert hashlib.sha256(serial).hexdigest()==rec['input_sha']
            assert rec['cut_messages']==r['message']+1
            old=r['viewed'];front=r['frontier'];doc={**old,**front};rs=model['ranks'];sc=model['scores']
            assert not set(old)&set(front) and len(front)<=64 and all(v['last']<r['index'] for v in front.values())
            for p,v in front.items():
                assert all(e['step']<r['index'] for e in v['sources'].values())
                distinct=any(a!=b and v['sources'][a]['call']!=v['sources'][b]['call'] for a in v['sources'] for b in v['sources'])
                assert sc['corroborated'][p]==distinct
            assert Counter(sc['shuffled'].values())==Counter(sc['corroborated'].values())
            assert rs['flat_recent']==sorted(doc,key=lambda p:(-doc[p]['last'],p))
            assert rs['bm25_all']==sortbag(sc['bm25'],doc) and rs['flat_union']==sortbag(sc['flat'],doc)
            for m,src in [('typed_union','corroborated'),('shuffled_union','shuffled')]:
                assert rs[m]==sortbag({p:v+.25*sc[src].get(p,False) for p,v in sc['flat'].items()},doc)
            for m,seq in rs.items():assert len(seq)==len(set(seq)) and set(seq)==(set(old) if m=='view_graph' else set(doc))
            ranking[r['id']]=(rs,set(old),set(front))
            total+=1;linkn+=len(front)
    assert total==459 and len(ranking)==459
    for panel,eps in evals.items():
        for ep,points in eps.items():
            if not points:continue
            agg=s[panel][ep];assert len(points)==agg['n'] and len({v['iid'] for v in points})==agg['tasks']
            assert sum(v['old_hit'] for v in points)==agg['old_oracle'] and sum(v['all_hit'] for v in points)==agg['union_oracle']
            for v in points:
                rs,old,new=ranking[v['id']];goal=set(v['targets'])
                assert bool(goal&old)==v['old_hit'] and bool(goal&(old|new))==v['all_hit']
                for m,names in rs.items():assert v['ranks'][m]==next((i for i,p in enumerate(names,1) if p in goal),0)
            for m,met in agg['methods'].items():
                ranks=[r['ranks'][m] for r in points]
                assert all(sum(0<v<=k for v in ranks)==met['h'+str(k)] for k in (1,3,6))
                assert abs(sum(1/v for v in ranks if v)/len(ranks)-met['mrr'])<1e-10
            for m,by in pairs[panel][ep].items():
                for metric,obj in by.items():
                    x=agg['methods']['typed_union'][metric]-agg['methods'][m][metric]
                    assert abs((x if metric=='mrr' else x/len(points))-obj['delta'])<1e-10
    print(json.dumps({'verified_anchors':total,'frontier_path_instances':linkn,'forecast_and_outcome_hashes':True}))
if __name__=='__main__':main()

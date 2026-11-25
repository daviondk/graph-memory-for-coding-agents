"""Frozen, gold-free predictions. Statement-only readers never see instrumented read cards."""
from bisect import bisect_left
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import gzip
import json
import random
from sources import D,C,read,dump,sha


class Origins:
    def __init__(self,events):
        self.values=[defaultdict(set) for _ in range(3)]
        self.generators=set()
        for ev in events:
            for desc in ev['write']:
                self.generators.add(ev['id'])
                for j,item in enumerate(desc):
                    if item is not None:self.values[j][item].add(ev['id'])
        self.generators=sorted(self.generators)
        self.values=[{k:sorted(v) for k,v in m.items()} for m in self.values]

    def earlier(self,field,key,t):
        v=self.values[field].get(key,[])
        return v[:bisect_left(v,t)],len(v)

    def shuffled(self,trace,t):
        points=self.generators[:bisect_left(self.generators,t)]
        shuffled=points.copy()
        random.Random(sha((trace+'::'+str(t)).encode())).shuffle(shuffled)
        return dict(zip(points,shuffled,strict=True))


def estimates(index,field,key,t):
    prev,total=index.earlier(field,key,t)
    unique=prev if len(prev)==1 else []
    return dict(universal=prev,append=unique,retract=unique if total==1 else [],latest=prev[-1:]),len(prev),total


def cards(trace,rows,events,idx):
    out=[]
    for c in rows:
        t=c['consumer'];v,name,scope=c['base']
        preds,live,final=estimates(idx,0,v,t)
        names=estimates(idx,1,name,t)[0];scopes=estimates(idx,2,scope,t)[0]
        ids=preds['universal']
        perm=idx.shuffled(trace,t)
        probe=random.Random(sha((trace+':candidate:'+c['id']).encode())).choice(ids) if ids else None
        preds.update(latest_any=sorted(perm)[-1:],latest_name=names['latest'],latest_binding=scopes['latest'],latest_binding_or_name=(scopes['latest'] or names['latest']),sham_latest_value=[perm[a] for a in preds['latest']],sham_append=[perm[a] for a in preds['append']],random_value=[] if probe is None else [probe])
        assert all(all(x<t for x in ss) for ss in preds.values())
        out.append(dict(id=c['id'],t=t,before=live,final=final,eligible_name=name is not None,eligible_scope=scope is not None,arms=preds))
    return out


def text_interface(trace,events,idx):
    out=[]
    for ev in events:
        t=ev['id'];perm=idx.shuffled(trace,t);arms={}
        for mode,field,keys in [('literal',0,ev['literals']),('symbol',1,ev['symbols'])]:
            candidate={k:set() for k in ('universal','append','retract','latest')}
            for key in keys:
                parti,*_=estimates(idx,field,key,t)
                for k,v in parti.items():candidate[k].update(v)
            for k,v in candidate.items():arms[mode+'_'+k]=sorted(v)
            arms[mode+'_sham_latest']=sorted(perm[p] for p in candidate['latest'])
        arms['latest_any']=sorted(perm)[-1:]
        assert all(all(a<t for a in v) for v in arms.values())
        out.append(dict(t=t,arms=arms))
    return out


def main():
    lock=read(D/'input-lock.json')
    p=C/'flow-packets.json';assert sha(p.read_bytes())==lock['packets']
    rows=[];events=cards_n=0
    for r in read(p):
        idx=Origins(r['events'])
        rec=dict(trace=r['trace'],text=text_interface(r['trace'],r['events'],idx),cards=cards(r['trace'],r['cards'],r['events'],idx))
        rows.append(rec);events+=len(rec['text']);cards_n+=len(rec['cards'])
    fp=D/'predictions.json.gz';data=(json.dumps(rows,sort_keys=True,separators=(',',':'))+'\n').encode()
    fp.write_bytes(gzip.compress(data,mtime=0))
    dump(D/'prediction-lock.json',dict(predictions=sha(fp.read_bytes()),packet=lock['packets'],input_lock=sha((D/'input-lock.json').read_bytes()),selector=sha(Path(__file__).read_bytes()),protocol=lock['protocol'],traces=len(rows),activities=events,cards=cards_n))
    print('sealed',len(rows),events,cards_n)
if __name__=='__main__':main()


from conditional import *
from common5 import *
from collections import defaultdict

def features(row,neural,key):
    def standard(s):return (s-s.mean())/max(s.std(),1e-5)
    scores=np.column_stack([row['graph'],row['owner'],row['lex'],neural])
    orders=[ordered(s) for s in scores.T]
    r=positions(orders);n=len(r)
    e=np.array(row['edgeinfo']);struct=np.c_[np.log1p(e[:,:3]),e[:,3:]]
    def direct(count):
        raw=scores[:,:count].copy();raw[:,2]=np.log1p(raw[:,2]);norm=np.column_stack([standard(c) for c in raw.T])
        inter=[1/(r[:,i]*r[:,j]) for i in range(count) for j in range(i+1,count)]
        return np.column_stack([basis(r[:,:count]),raw,norm,struct,*inter])
    base=direct(4);graphonly=direct(3)
    signal=np.array(neural);activation=(standard(signal).clip(-3,3)+3)/6
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for a,b,amb,pre in row['links']:
        incoming[b].append((a,amb,pre));outgoing[a].append((b,amb,pre))
    def aggregate(edges,i,deg):
        msg=edges[i]
        if not msg:return [0.]*6
        weighted=[activation[j]*w for j,w,_ in msg]
        precedent=[activation[j]*w for j,_,w in msg]
        debias=[s/(1+len(deg[j]))**.5 for s,(j,_,_) in zip(weighted,msg)]
        return [max(weighted),np.mean(weighted),max(precedent),np.mean(precedent),max(debias),max(weighted)*activation[i]]
    extra=np.array([aggregate(incoming,i,outgoing)+aggregate(outgoing,i,incoming) for i in range(n)])
    return {'direct':base,'edge':np.c_[base,extra],'placebo':np.c_[base,shuffled(extra,key)],'no_encoder':graphonly},dict(graph=orders[0],owner=orders[1],bm25=orders[2],unix=orders[3],rrf=ordered(np.sum(1/(60+r),axis=1)),graph_unix_rrf0=ordered(1/r[:,0]+1/r[:,3]))

def main():
    datasets={};fixed={}
    for tag,path,pred in [('dev',D/'struct_dev.jsonl.gz',E/'predictions.jsonl.gz'),('test',D/'struct_test.jsonl.gz',D/'new_encoder.jsonl.gz')]:
        reader={(row['panel'],row['idx'],int(row['query'])):row for row in rr(pred) if str(row['query']) in ('3','10')}
        datasets[tag]={}
        for row in rr(path):
            key=row['panel'],row['idx'],row['query'];neural=reader[key];f,baseline=features(row,neural['cosine'],'|'.join(map(str,key)))
            assert baseline['unix']==neural['rank']
            datasets[tag][key]=(row['project'],f,baseline)
    old={(p,j,k):arms['graph'] for p,j,k,project,sz,h,e,arms in rr(R/'strict_java.pred.jsonl.gz')}
    graph_mismatch=sum(old[key]!=v[2]['graph'] for key,v in datasets['dev'].items())
    assert graph_mismatch==0,graph_mismatch
    y={(z['panel'],z['idx'],z['keep']):z['gold'] for z in rr(E/'scores.jsonl.gz')}
    assert not {v[0] for v in datasets['dev'].values()}&{v[0] for v in datasets['test'].values()}
    dump('neural_method_lock.json',dict(utc=now(),hashes={str(p):filehash(p) for p in [D/'PROTOCOL_RU.md',D/'neural_rank.py',D/'conditional.py',D/'graph_data.py',D/'struct_dev.jsonl.gz',D/'struct_test.jsonl.gz',E/'scores.jsonl.gz',E/'predictions.jsonl.gz',D/'new_encoder.jsonl.gz',R/'models.pkl']},graph_mismatch=graph_mismatch,l2=.02))
    models={};pred=[]
    for k in (3,10):
        train=[(key,v) for key,v in datasets['dev'].items() if key[2]==k];gold=[y[key] for key,v in train];sizes=[len(v[2]['graph']) for key,v in train]
        mods={arm:fit(np.concatenate([v[1][arm] for _,v in train]),sizes,gold,.02) for arm in ('direct','edge','placebo','no_encoder')}
        models[str(k)]=mods
        for (panel,idx,query),(project,f,baseline) in datasets['test'].items():
            if query!=k:continue
            pred.append(dict(panel=panel,idx=idx,query=k,project=project,orders={**baseline,**{arm:ordered(f[arm]@np.asarray(m['weights'])) for arm,m in mods.items()}}))
    dump('neural_weights.json',models);jsonrows('neural_predictions.jsonl.gz',pred)
    dump('neural_decisions.json',dict(utc=now(),rows=len(pred),pred=filehash(D/'neural_predictions.jsonl.gz'),weights=filehash(D/'neural_weights.json')))
if __name__=='__main__':main()


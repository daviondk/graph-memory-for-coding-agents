from neural_rank import features
from conditional import fit,np
from common5 import *
def main():
    p=E/'predictions.jsonl.gz'
    reader={(r['panel'],r['idx'],int(r['query'])):r for r in rr(p) if str(r['query']) in ('3','10')}
    y={(r['panel'],r['idx'],r['keep']):r['gold'] for r in rr(E/'scores.jsonl.gz')}
    old={(p,j,k):a['graph'] for p,j,k,_,_,_,_,a in rr(R/'strict_java.pred.jsonl.gz')}
    sets={3:[],10:[]};mismatch=[]
    for row in rr(D/'struct_dev.jsonl.gz'):
        key=row['panel'],row['idx'],row['query'];nr=reader[key]
        f,b=features(row,nr['cosine'],'|'.join(map(str,key)))
        assert nr['rank']==b['unix']
        if old[key]!=b['graph']:mismatch.append(key)
        sets[key[-1]].append((f,len(b['graph']),y[key]))
    assert not mismatch,mismatch[:5]
    weights={}
    for q,data in sets.items():
        fs,sz,gold=zip(*data)
        weights[str(q)]={name:fit(np.concatenate([f[name] for f in fs]),sz,gold,.02) for name in ('direct','edge','placebo','no_encoder')}
    dump('neural_preregistered_weights.json',weights)
    dump('neural_devlock.json',dict(utc=now(),rows=len(y),difference=0,sha=filehash(D/'neural_preregistered_weights.json'),inference=filehash(D/'neural_rank.py'),features=filehash(D/'graph_data.py'),encoder=filehash(D/'embed.py'),fit=filehash(D/'conditional.py')))
if __name__=='__main__':main()


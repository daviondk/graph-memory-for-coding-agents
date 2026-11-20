"""Packets for the paired no-message and message readers. No gold labels are loaded."""
from conditional import *
from common5 import *
import pickle,sys,math
sys.path.insert(0,str(R))
from memory import encode,features,pp,cos

def main():
    models=pickle.loads((R/'models.pkl').read_bytes())
    for split,path in [('dev',E/'blind.jsonl.gz'),('test',D/'blind_new.jsonl.gz')]:
        def generate():
            for row in rr(path):
                enc=encode(row['candidates']);_,edges,outgoing,_=enc
                for k in (3,10):
                    q=row['queries'][str(k)];x=features(q+'\n',enc,k);qp=pp(q)
                    scores=[models[k,name].predict_proba(x[:,:n])[:,1].tolist() for name,n in [('graph',43),('owner',35)]]
                    links=[]
                    for dest,items in enumerate(edges):
                        by={}
                        for src,prior,ambiguity in items:
                            old=by.get(src,(0.,0.));by[src]=(max(old[0],ambiguity),max(old[1],cos(qp,prior)*ambiguity))
                        for src,(a,p) in sorted(by.items()):links.append([src,dest,a,p])
                    yield dict(panel=row['panel'],idx=row['idx'],project=row['project'],query=k,graph=scores[0],owner=scores[1],lex=x[:,0].tolist(),edgeinfo=x[:,35:].tolist(),links=links)
        jsonrows('struct_'+split+'.jsonl.gz',generate())
if __name__=='__main__':main()


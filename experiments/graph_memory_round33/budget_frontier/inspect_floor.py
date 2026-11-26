"""Decompose short-budget differences using the actual strictly packed prefixes."""
from collections import defaultdict
from frontier import *
def main():
    ranks=load(HERE/"test-ranks.json.gz");cells=load(HERE/"test-outcomes.json.gz");features=load(PRIVATE/"test.json.gz");table={}
    for b in (256,512):
        groups=defaultdict(list);i=B.index(b)
        for r in features:
            q=r["q"];cost=r["c"];arms=cells[q]["methods"]
            base=prefix(ranks[q]["a0"],cost,b);adjusted=prefix(ranks[q]["a4"],cost,b)
            k=("read" if base else "empty")+"/"+("read" if adjusted else "empty")
            c0,c1=arms["a0"]["c"][i],arms["a4"]["c"][i]
            assert base or c0==0;assert adjusted or c1==0
            groups[k].append([c1-c0,len(base),len(adjusted)])
        table[str(b)]={g:{"n":len(a),"contribution_pp":float(100*np.sum(a,axis=0)[0]/len(features)),"mean_nodes":np.mean(a,axis=0)[1:].tolist()} for g,a in groups.items()}
    save(HERE/"floor.json",{"test":sha(HERE/"test-outcomes.json.gz"),"groups":table})
if __name__=="__main__":main()

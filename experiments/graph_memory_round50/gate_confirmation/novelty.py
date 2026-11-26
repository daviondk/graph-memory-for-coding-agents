from paths_a import *
from panel import norm
def main():
    prior1=get(A/"novelty.json.gz");fresh=get(P/"visible.json.gz");cat=get(D/"catalog-receipts.json.gz")
    previous={**prior1["old"],**prior1["new"]};assert len(previous)==1280
    current={}
    for q,(txt,docs) in fresh.items():
        i=cat[q]["first"];current[q]=[hexb(norm(txt).encode()),hexb((docs[i][1]+"\0"+docs[i][2]).encode())]
    assert len(current)==1280 and not set(current)&set(previous)
    for j in (0,1):
        assert len({v[j] for v in current.values()})==1280
        assert not {v[j] for v in previous.values()}&{v[j] for v in current.values()}
    put(D/"novelty.json.gz",dict(historical=previous,new=current,source=sha(A/"novelty.json.gz")))
if __name__=="__main__":main()

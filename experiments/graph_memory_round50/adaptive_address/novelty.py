from paths_a import *
from panel import norm
def main():
    old=get(OLD/"visible.json.gz");new=get(P/"visible.json.gz");prior=get(REP/"contexts.json.gz");now=get(D/"catalog-receipts.json.gz")
    def row(v,i):
        title,body=v[1][i][1:];return [hexb(norm(v[0]).encode()),hexb((title+"\0"+body).encode())]
    older={q:row(v,prior[q]["seed"]) for q,v in old.items()};fresh={q:row(v,now[q]["first"]) for q,v in new.items()}
    assert not set(older)&set(fresh)
    for col in [0,1]:assert not {v[col] for v in older.values()}&{v[col] for v in fresh.values()}
    put(D/"novelty.json.gz",dict(old=older,new=fresh))
if __name__=="__main__":main()

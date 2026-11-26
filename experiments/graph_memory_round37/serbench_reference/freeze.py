"""Join external ranking scores to already fixed state and candidate identifiers."""
from common import D,R34,data,get,np,save,sha
def main():
    strong=R34/"strong/test-ranks.json.gz";raw=get(strong)
    assert sha(strong)==get(R34/"strong/seal.json")["forecasts"]
    s=get(D/"reranker-scores.json.gz"); m=get(D/"mmr-predictions.json.gz")
    assert raw.keys()==s.keys()==m.keys() and len(s)==214
    f=data();pred={}
    for q,old in raw.items():
        assert f[q]["split"]=="test";dense=old["dense_state"]
        pairs=s[q];assert len(pairs)==32 and [p[1] for p in pairs]==dense[:32]
        assert all(np.isfinite(p[2]) for p in pairs)
        cross=[p[1] for p in sorted(pairs,key=lambda p:(-p[2],p[0]))]
        chosen={key:old[key][:8] for key in ("bm25","dense_state","union_cost")}
        chosen.update(mmr=m[q],cross_encoder=cross[:8])
        assert all(len(set(seq))==8 and min(seq)>=0 and max(seq)<len(f[q]["ids"]) for seq in chosen.values())
        pred[q]={model:[f[q]["ids"][i] for i in seq] for model,seq in chosen.items()}
    dest=D/"predictions.json.gz";save(dest,pred)
    files=("PROTOCOL_RU.md","availability.json","reranker-scores.json.gz","mmr-predictions.json.gz","mmr-dev.json","predictions.json.gz","common.py","rerank.py","mmr.py","freeze.py")
    save(D/"seal.json",dict(files={n:sha(D/n) for n in files},r34_forecasts=sha(strong)))
if __name__=="__main__":main()

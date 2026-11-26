"""Export CPU evidence scores and anonymous numeric features for held-out reproducibility, without text/tokens."""
from common import *
from matched_fit import inputs,features,rank_ids
def main():
    seal=read(OUT/"matched-seal.json");frozen=read(OUT/"matched-predictions.json.gz");m=read(OUT/"matched-weights.json")
    assert seal["weights"]==sha(OUT/"matched-weights.json") and seal["forecasts"]==sha(OUT/"matched-predictions.json.gz")
    t=inputs();tok=t["tokens"];out={}
    for q,arms in frozen.items():
        v=t["states"][q];docs=[tok[k][1] for k in v["doc"]];raw={}
        for typ in ("three","nine"):
            z=features(docs,tok[v[typ]][1]);model=m[typ]
            scaled=(z-np.array(model["mean"]))/np.array(model["scale"])
            y=scaled@np.array(model["coef"])+model["intercept"][0]
            for n,sc in (("lr",y),("bm",z[:,0])):
                k=n+typ;assert rank_ids(sc,v["ids"])==arms[k] and rank_ids(sc,v["ids"],v["seen"])==arms[k+"_seen"]
            raw[typ]=dict(x=z.tolist(),scores=y.tolist())
        out[q]=dict(ids=v["ids"],seen=v["seen"],values=raw)
    save("matched-numeric.json.gz",out)
    print("Reconstructed both logistic models, all lexical scores and top-8 predictions for",len(out),"states.")
if __name__=="__main__":main()

"""Score sealed admission decisions and account for running the base reader."""
from collections import defaultdict
from pathlib import Path
from statistics import fmean
import sys
import numpy as np
from trigger import HERE,PREVIOUS,read,save,sha

def main():
    forecasts=read(HERE/"routes.json.gz");reference=read(PREVIOUS/"per-query.json.gz");cost=read(HERE/"costs.json.gz")
    assert sha(HERE/"routes.json.gz")==read(HERE/"route-seal.json")["routes"]
    names=list(next(iter(forecasts.values()))["online"]);out={};rng=np.random.default_rng(28801)
    articles=sorted({r["title"] for r in forecasts.values()});resample=rng.integers(0,len(articles),size=(20000,len(articles)))
    details={}
    for mode in ("online","batch"):
        values=defaultdict(list)
        for q,r in sorted(forecasts.items()):
            base=reference[q]["arms"]["base"];more=reference[q]["arms"]["both"]
            before,after,delta=cost[q]["model"]
            decisions={**r[mode],"always":1,"never":0}
            for method,admit in decisions.items():
                score=more if admit else base
                values[method].append((q,r["title"],admit,score["f1"],score["em"],cost[q]["extra"]*admit,
                    cost[q]["ranges"]*admit,before+admit*after,before+admit*delta,after,
                    int(admit and more["f1"]>base["f1"]),int(admit and more["f1"]<base["f1"])))
        metrics={}
        for m,v in values.items():
            metrics[m]={"n":len(v),"opened":sum(x[2] for x in v),"f1":100*fmean(x[3] for x in v),
                "em":100*fmean(x[4] for x in v),"mean_read_tokens":fmean(x[5] for x in v),"ranges":sum(x[6] for x in v),
                "total_if_fresh":sum(x[7] for x in v),"total_if_reuse":sum(x[8] for x in v),
                "direct_both_tokens":sum(x[9] for x in v),"wins_vs_base":sum(x[10] for x in v),"losses_vs_base":sum(x[11] for x in v)}
        contrasts={}
        for m,b in (("gain","low_score"),("gain","error"),("low_score","hash"),("gain","always"),("low_score","always")):
            grouped=defaultdict(list)
            for x,y in zip(values[m],values[b]):
                assert x[:2]==y[:2];grouped[x[1]].append(x[3]-y[3])
            dif=np.array([100*fmean(grouped[a]) for a in articles]);boot=dif[resample].mean(axis=1)
            contrasts[m+"-"+b]={"delta":float(dif.mean()),"ci95":np.quantile(boot,[.025,.975]).tolist(),
                "wins":sum(x[3]>y[3] for x,y in zip(values[m],values[b])),"losses":sum(x[3]<y[3] for x,y in zip(values[m],values[b]))}
        out[mode]={"summary":metrics,"contrasts":contrasts}
        details[mode]={m:[[x[0],*x[2:]] for x in values[m]] for m in values}
    save(HERE/"outcomes.json.gz",details);save(HERE/"results.json",{"routes":sha(HERE/"route-seal.json"),"outcomes":sha(HERE/"outcomes.json.gz"),"results":out})
    for mode,v in out.items():
        print(mode, {m:[s["opened"],round(s["f1"],2),s["total_if_reuse"]] for m,s in v["summary"].items()},v["contrasts"]["gain-low_score"])
if __name__=="__main__":main()


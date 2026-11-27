"""Score frozen ARB top-five file-address lists, including inactive strata."""
from collections import Counter
from statistics import fmean
import numpy as np

from predict import HERE,OLD,digest,read,save
from grade import metrics

def main():
    seal=read(HERE/"seal.json")
    for root,files in ((HERE,seal["local"]),(OLD,seal["inputs"])):
        assert all(digest(root/k)==v for k,v in files.items())
    data=read(HERE/"ranks.json.gz");gold=read(OLD/"ground-truth.json.gz");grades={}
    for q,row in data.items():
        values={m:metrics(rs,gold[q]) for m,rs in row["ranks"].items()}
        values["oko_mean"]=[fmean(vals) for vals in zip(*(values["oko"+str(i)] for i in (1,2,3)))]
        grades[q]=values
    def group(name,selected):
        if not selected:return {"n":0}
        keys=list(grades[selected[0]])
        means={m:[fmean(seq) for seq in zip(*(grades[q][m] for q in selected))] for m in keys}
        ds=np.array([grades[q]["pair"][0]-grades[q]["linear"][0] for q in selected])
        rr,idx=np.unique([data[q]["repo"] for q in selected],return_inverse=True)
        ns=np.bincount(idx);sums=np.bincount(idx,weights=ds)
        rng=np.random.default_rng(57063);reps=rng.multinomial(len(rr),[1/len(rr)]*len(rr),size=20000)
        delta=(reps@sums)/(reps@ns)
        def n_if(condition):return sum(condition(data[q]) for q in selected)
        return dict(n=len(selected),repos=len(rr),means=means,delta=float(ds.mean()),
            ci=np.quantile(delta,[.025,.975]).tolist(),wins=int((ds>1e-12).sum()),
            losses=int((ds< -1e-12).sum()),ties=int((abs(ds)<=1e-12).sum()),
            graph_order_changed=n_if(lambda r:r["graph"]!=r["graph_pair"]),
            graph_top20_order_changed=n_if(lambda r:r["graph"][:20]!=r["graph_pair"][:20]),
            final_order_changed=n_if(lambda r:r["ranks"]["linear"]!=r["ranks"]["pair"]),
            final_set_changed=n_if(lambda r:set(r["ranks"]["linear"])!=set(r["ranks"]["pair"])),
            extra_covered=sum(len((set(data[q]["ranks"]["pair"])-set(data[q]["ranks"]["linear"]))&set(gold[q])) for q in selected),
            lost_covered=sum(len((set(data[q]["ranks"]["linear"])-set(data[q]["ranks"]["pair"]))&set(gold[q])) for q in selected),
            reads=sum(data[q]["event_count"] for q in selected),members=sum(data[q]["members"] for q in selected),
            multi_test_events=sum(data[q]["multi_test_events"] for q in selected))
    filters=dict(all=lambda r:True,multiple_seeds=lambda r:len(r["seeds"])>=2,
                 multi_event=lambda r:r["multisource"],multi_test=lambda r:r["test_supported"]>0,
                 changed=lambda r:r["ranks"]["linear"]!=r["ranks"]["pair"])
    outputs={k:group(k,[q for q,r in data.items() if predicate(r)]) for k,predicate in filters.items()}
    save(HERE/"graded.json.gz",grades);save(HERE/"results.json",outputs)
    print({g:(o["n"],o.get("final_order_changed"),o.get("final_set_changed"),o.get("graph_order_changed"),o.get("delta")) for g,o in outputs.items()})
    print("reads",outputs["all"]["reads"],outputs["all"]["members"],"all means",outputs["all"]["means"])
if __name__=="__main__":main()

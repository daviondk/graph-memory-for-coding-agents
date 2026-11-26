"""Direct author forward with batched, untrimmed encoder after both original beam roots disappear."""
from pathlib import Path
import sys,time
from run import HERE,sha,put,read,inputs,load_model,predict

def main():
    import torch,psutil
    from transformers import DebertaV2Model
    plan=read(HERE/"plan.json")
    subset=[plan["panel"][i] for i in (1,5)]
    if "lock" in sys.argv:
        put(HERE/"stock-plan.json",{"panel":subset,"prior":sorted(p.stem for p in (HERE/"forecasts").glob("*.json")),
            "code":sha(Path(__file__)),"conditions":["no deletions","delete both initial roots"],"beam":2,"threads":2})
        return
    gate=read(HERE/"stock-plan.json")
    assert gate["panel"]==subset and sha(Path(__file__))==gate["code"]
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    proc=psutil.Process()
    if hasattr(psutil,"BELOW_NORMAL_PRIORITY_CLASS"):proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    data=inputs()
    model,tok,_=load_model()
    model.encoder.forward=DebertaV2Model.forward.__get__(model.encoder,type(model.encoder))
    rows={}
    for q in subset:
        path=HERE/"forecasts"/(q+".json")
        while not path.is_file():time.sleep(5)
        f=read(path)["full"];conditions={}
        for label,banned in (("full",set()),("both_roots",set(f["doc_order"][:2]))):
            keep=[i for i in range(10) if i not in banned];roots=[i for i in f["doc_order"] if i in keep][:2]
            started=time.monotonic()
            actual=predict(model,tok,data[q],keep,2)
            expected=[x for x in f["pairs"] if not set(x[:2])&banned and set(x[:2])&set(roots)]
            tx={tuple(x[:2]):x[2] for x in expected};obs={tuple(x[:2]):x[2] for x in actual["pairs"]}
            matched=tx.keys()==obs.keys()
            error=max(abs(tx[k]-obs[k]) for k in tx.keys()&obs.keys()) if tx.keys()&obs.keys() else None
            rec={"matched_keys":matched,"same_winner":set(actual["native_top"][0])==set(expected[0][:2]),"expected_beam":roots,
                 "direct_beam":actual["doc_order"],"max_pair_abs":error,"sec":time.monotonic()-started,"count":len(tx),
                 "peak_rss_bytes":getattr(proc.memory_info(),"peak_wset",proc.memory_info().rss),"direct":actual}
            conditions[label]=rec
            print(q,label,{k:v for k,v in rec.items() if k!="direct"},flush=True)
        rows[q]=conditions
        put(HERE/"stock-probe.json",{"plan":sha(HERE/"stock-plan.json"),"rows":rows})
if __name__=="__main__":main()

"""Official SQuAD scoring after all predictions, plus measurements of source-address coverage."""
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
from contexts28 import D,P,R26,ARMS,read,save,sha,h
import importlib.util
score_spec=importlib.util.spec_from_file_location("r26_answer_score",R26/"score.py")
upstream=importlib.util.module_from_spec(score_spec);score_spec.loader.exec_module(upstream)
def width(spans):return sum(b-a for a,b in upstream.union(spans))
def contrasts(rows,metric):
    group=defaultdict(list);all_d=[]
    for r in rows.values():
        old=r["arms"][ARMS[0]][metric];new=r["arms"][ARMS[1]][metric];delta=old-new
        group[r["title"]].append(delta);all_d.append(delta)
    assert len(group)==48 and all(len(v)==12 for v in group.values())
    means=np.array([np.mean(v) for k,v in sorted(group.items())]);gen=np.random.default_rng(280347)
    boots=means[gen.integers(48,size=(20000,48))].mean(axis=1)
    return dict(delta_pp=float(means.mean()*100),ci95_pp=(100*np.quantile(boots,[.025,.975])).tolist(),
        wins=sum(x>1e-12 for x in all_d),losses=sum(x< -1e-12 for x in all_d),ties=sum(abs(x)<=1e-12 for x in all_d),
        articles_changed=sum(any(abs(x)>1e-12 for x in v) for v in group.values()))
def main():
    fs=read(D/"forecast-seal.json");assert fs["forecasts"]==sha(D/"predictions.json.gz") and fs["cfg"]["input_seal"]==sha(D/"context-seal.json")
    assert read(D/"context-seal.json")["contexts"]==sha(D/"contexts.json.gz")
    off=upstream.scorer();raw=read(upstream.RAW);rr=read(D/"contexts.json.gz");pred=read(D/"predictions.json.gz");out={};ps=[]
    predicted={k:{} for k in ARMS};geometries=Counter()
    for art in raw["data"]:
        src="\n\n".join(z["context"] for z in art["paragraphs"]);t=art["title"];pos=0;pars=[]
        for para in art["paragraphs"]:
            keep=[]
            for qa in para["qas"]:
                q=qa["id"]
                if q not in rr:continue
                keep.append(qa);r=rr[q];assert r["title"]==t
                gold={(pos+x["answer_start"],pos+x["answer_start"]+len(x["text"])) for x in qa["answers"]}
                ref=[x["text"] for x in qa["answers"]]
                assert all(src[pos+x["answer_start"]:pos+x["answer_start"]+len(x["text"])]==x["text"] for x in qa["answers"])
                obs={};base=[(l,z) for l,z,_ in r["base"]];original=width(base)
                for arm in ARMS:
                    p=pred[q]["outputs"][arm];a=r["arms"][arm];l,z=p["start"],p["end"];answer=src[l:z]
                    assert h(answer)==p["answer_sha"] and a["wire_sha"]==p["receipt"]
                    extra=[(l,z) for l,z,_ in a["extra"]];spans=base+extra;s,e=spans[p["body_index"]]
                    assert s<=l<z<=e
                    predicted[arm][q]=answer;sent=sum(z-l for l,z in extra)
                    obs[arm]=dict(f1=off.metric_max_over_ground_truths(off.f1_score,answer,ref),
                        em=int(off.metric_max_over_ground_truths(off.exact_match_score,answer,ref)),
                        correct_coordinates=int((l,z) in gold),any_fragment=int(any(i<=x<y<=j for x,y in gold for i,j in spans)),
                        any_union=int(any(i<=x<y<=j for x,y in gold for i,j in upstream.union(spans))),
                        native_extra=a["native"],uncased_extra=a["uncased"],total_wire=a["wire_native"],model_tokens=p["logical_tokens"],windows=p["windows"],
                        new_chars=width(spans)-original,source_chars=sent,extra_ranges=len(extra),winner_in_extra=int(p["body_index"]>=len(base)))
                assert obs[ARMS[0]]["model_tokens"]==obs[ARMS[1]]["model_tokens"] and obs[ARMS[0]]["native_extra"]==obs[ARMS[1]]["native_extra"]
                out[q]={"title":t,"arms":obs}
                left,right=obs["both"],obs["boundary_window"]
                geom=left["any_union"]-right["any_union"];performance=np.sign(left["f1"]-right["f1"]);geometries[str((int(geom),int(performance)))]+=1
            if keep:pars.append({"qas":keep})
            pos+=len(para["context"])+2
        if pars:ps.append({"paragraphs":pars})
    assert len(out)==576 and len(ps)==48
    aggregate={};numeric=("f1","em","correct_coordinates","any_fragment","any_union","native_extra","uncased_extra","total_wire","model_tokens","windows","new_chars","source_chars","extra_ranges","winner_in_extra")
    for k in ARMS:
        arr=[r["arms"][k] for r in out.values()];res={field:float(np.mean([v[field] for v in arr])) for field in numeric}
        std=off.evaluate(ps,predicted[k]);assert abs(std["f1"]-res["f1"]*100)<1e-8 and abs(std["exact_match"]-res["em"]*100)<1e-8
        res["official"]=std;res["counts"]={f:sum(v[f] for v in arr) for f in ("em","correct_coordinates","any_fragment","any_union","new_chars","source_chars","extra_ranges","winner_in_extra")}
        res["new_fraction_weighted"]=res["counts"]["new_chars"]/res["counts"]["source_chars"]
        aggregate[k]=res
    con={f:contrasts(out,f) for f in ("f1","em","any_fragment","any_union","correct_coordinates")}
    save(D/"per-query.json.gz",out);save(D/"results.json",dict(aggregate=aggregate,both_minus_boundary=con,coverage_change_vs_qa=geometries,n=len(out),
          articles=len(ps),same_native_budget=len(out),same_model_cost=len(out),per_query=sha(D/"per-query.json.gz"),model_seal=sha(D/"forecast-seal.json"),code=sha(Path(__file__))))
    print({k:v["official"] for k,v in aggregate.items()},con["f1"],flush=True)
if __name__=="__main__":main()

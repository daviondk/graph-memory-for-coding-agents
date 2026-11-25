"""Use the official v1.1 scoring functions after predictions seal, with article-cluster uncertainty."""
from collections import defaultdict
import importlib.util,json
import numpy as np
from prepare import D,P,ARMS,RAW,read,save,sha,h,Path
def scorer():
    path=P/"official.py";assert sha(path)=="f5a673dbbd173e29e9ea38f1b2091d883583b77b3a4c17144b223fb0f2f9bd09"
    sp=importlib.util.spec_from_file_location("official_squad",path);mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod);return mod
def union(intervals):
    out=[]
    for l,r in sorted(intervals):
        if out and l<=out[-1][1]:out[-1][1]=max(r,out[-1][1])
        else:out.append([l,r])
    return out
def ci(rows,k,j,field):
    groups=defaultdict(list);allx=[]
    for _,r in rows.items():
        x=r["arms"][k][field]-r["arms"][j][field];groups[r["title"]].append(x);allx.append(x)
    n=len(groups);assert {len(a) for a in groups.values()}=={12}
    g=np.array([np.mean(v) for _,v in sorted(groups.items())]);rng=np.random.default_rng(260731)
    boot=g[rng.integers(n,size=(20000,n))].mean(axis=1)
    return dict(delta_pp=100*float(g.mean()),ci95_pp=(100*np.quantile(boot,[.025,.975])).tolist(),
                ci97_5_pp=(100*np.quantile(boot,[.0125,.9875])).tolist(),wins=sum(x>1e-12 for x in allx),
                losses=sum(x< -1e-12 for x in allx),ties=sum(abs(x)<=1e-12 for x in allx),
                articles_with_any_change=sum(any(abs(x)>1e-12 for x in g) for g in groups.values()))
def main():
    official=scorer();seal=read(D/"forecast-seal.json");raw=read(RAW)
    contexts=read(D/"contexts.json.gz");assert seal["forecasts"]==sha(D/"predictions.json.gz")
    assert seal["config"]["inputs"]==sha(D/"input-lock.json") and read(D/"input-lock.json")["contexts"]==sha(D/"contexts.json.gz")
    preds=read(D/"predictions.json.gz");view=read(P/"blind-input.json.gz");assert set(contexts)==set(preds)
    observations={};payload=[];standard={a:{} for a in ARMS};mismatch=0
    for art in raw["data"]:
        title=art["title"];t=view["docs"][title];ps=[];anch=0
        for para in art["paragraphs"]:
            ptext=para["context"];assert t[anch:anch+len(ptext)]==ptext;questions=[]
            for qa in para["qas"]:
                q=qa["id"]
                if q not in preds:continue
                r=contexts[q];assert r["title"]==title
                texts=[a["text"] for a in qa["answers"]];gold=[]
                for a in qa["answers"]:
                    lo=anch+a["answer_start"];hi=lo+len(a["text"])
                    if t[lo:hi]==a["text"]:gold.append((lo,hi))
                    else:mismatch+=1
                item={"title":title,"arms":{},"references":len(texts),"verifiable":len(gold)}
                for k in ARMS:
                    action=r["arms"][k];p=preds[q]["arms"][k];assert p["receipt"]==action["wire_sha"]
                    l,hi=p["start"],p["end"];s=t[l:hi];assert h(s)==p["answer_sha"]
                    records=r["base"]+action["extra"];periods=[(a,b) for a,b,_ in records];position=p["body_index"]
                    assert periods[position][0]<=l<hi<=periods[position][1];assert p["answer_tokens"]<=30
                    visible=union(periods);maxrefs=official.metric_max_over_ground_truths
                    em=int(maxrefs(official.exact_match_score,s,texts));f1=maxrefs(official.f1_score,s,texts)
                    item["arms"][k]=dict(em=em,f1=f1,correct_address=int((l,hi) in gold),
                        has_annotated_span=int(any(a<=x<y<=b for x,y in gold for a,b in visible)),
                        extractable_fragment=int(any(a<=x<y<=b for x,y in gold for a,b in periods)),wire_tokens=action["native_wire"],
                        native_extra=action["native_extra"],unc_extra=action["unc_extra"],model_windows=p["windows"],logical_tokens=p["logical_tokens"],
                        starts_in_open=int(position>=len(r["base"])),returned_tokens=p["answer_tokens"])
                    standard[k][q]=s
                observations[q]=item;questions.append(qa)
            if questions:ps.append({"qas":questions})
            anch+=len(ptext)+2
        if ps:payload.append({"paragraphs":ps})
    assert len(observations)==576 and len(payload)==48
    aggregate={}
    for k in ARMS:
        arr=[r["arms"][k] for r in observations.values()];o=official.evaluate(payload,standard[k])
        res={field:float(np.mean([a[field] for a in arr])) for field in arr[0]}
        assert abs(res["f1"]*100-o["f1"])<1e-8 and abs(res["em"]*100-o["exact_match"])<1e-8
        res.update(official=o,counts={f:sum(r[f] for r in arr) for f in ("em","correct_address","has_annotated_span","extractable_fragment","starts_in_open")})
        aggregate[k]=res
    con={}
    for k,j in (("both","right"),("both","adaptive"),("adaptive","right"),("both","base"),("right","base"),("adaptive","base")):
        con[k+"-"+j]={m:ci(observations,k,j,m) for m in ("f1","em","has_annotated_span","extractable_fragment","correct_address")}
    save(D/"per-query.json.gz",observations)
    save(D/"results.json",dict(n=len(observations),articles=len(payload),aggregate=aggregate,contrasts=con,forecast_seal=sha(D/"forecast-seal.json"),
         aligned_spans_mismatch=mismatch,per_query=sha(D/"per-query.json.gz"),code=sha(Path(__file__)),evaluator=sha(P/"official.py"),
         n_equal_native=sum(len({r["arms"][k]["wire_tokens"] for k in ARMS[1:]})==1 for r in observations.values()),
         n_equal_model_compute=sum(len({r["arms"][k]["logical_tokens"] for k in ARMS[1:]})==1 for r in observations.values())))
    print({k:v["official"] for k,v in aggregate.items()},con["both-right"]["f1"],con["both-adaptive"]["f1"])
if __name__=="__main__":main()

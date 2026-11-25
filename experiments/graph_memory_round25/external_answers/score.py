"""Score locked predictions. Reader-facing code does not import this file or the gold annotations."""
from collections import Counter,defaultdict
import importlib.util, json
from pathlib import Path
import numpy as np
from scipy.stats import binomtest
from prepare import D,PRIVATE,RAW,read,write,sha,h,make_fields,Tokenizer,TOK,paid_open
ARMS=("base","replay","old","edge")
def read_official():
    p=PRIVATE/"qasper_evaluator.py"
    assert sha(p)=="781aba7cd8e524bef4f0a1b4bf3504e5b02cb1d8d5bf32a8f0a89dfa83e86bfe"
    spec=importlib.util.spec_from_file_location("ai2_qasper",p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def union(ranges):
    merged=[]
    for a,b in sorted(ranges):
        if b<=a:continue
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    return merged
def coverage(pars,scopes,sets):
    covered=defaultdict(list)
    for d,a,b in scopes:covered[d].append((a,b))
    covered={d:union(v) for d,v in covered.items()}
    coverage_by_text=defaultdict(int)
    for d,a,b,s in pars:
        ov=sum(max(0,min(h,b)-max(l,a)) for l,h in covered.get(d,[]))
        coverage_by_text[s]=max(coverage_by_text[s],ov)
    touched=sorted(s for s,ov in coverage_by_text.items() if ov>0)
    vals=[]
    for ann in sets:
        evidence=set(ann["evidence"]);size=sum(map(len,evidence))
        if not size:continue
        vals.append(sum(coverage_by_text[s] for s in evidence)/size)
    return touched,max(vals,default=None)
def estimate(rows,key):
    v=np.array(rows,dtype=float);rng=np.random.default_rng(25046);res=rng.integers(len(v),size=(20000,len(v)))
    return dict(n=len(v),delta_pp=100*float(v.mean()),ci95_pp=(100*np.quantile(v[res].mean(axis=1),[.025,.975])).tolist(),
                wins=int((v>1e-12).sum()),losses=int((v< -1e-12).sum()),ties=int((abs(v)<=1e-12).sum()))
def avg(v):
    return float(np.mean(v)) if v else None
def main():
    lock=read(D/"input-lock.json");seal=read(D/"forecast-seal.json")
    assert seal["config"]["input_lock"]==sha(D/"input-lock.json")
    for p,key in ((D/"contexts.json.gz","contexts"),(RAW,"raw"),(D/"selection.json","selection")):assert sha(p)==lock[key]
    assert sha(PRIVATE/"outputs.json.gz")==seal["private_outputs"] and sha(D/"forecasts.json.gz")==seal["forecasts"]
    preds=read(PRIVATE/"outputs.json.gz");public=read(D/"forecasts.json.gz");ctx=read(D/"contexts.json.gz")
    for k,p in preds.items():assert h(p.get("answer",""))==public[k]["answer_sha"]
    source=read(RAW);n_all=sum(len(v["qas"]) for v in source.values());off=read_official()
    gold=off.get_answers_and_evidence(source,True);wp=Tokenizer.from_file(str(TOK))
    outcome={};all_preds={k:{} for k in ARMS};unique_ids=set()
    for q,r in ctx.items():
        doc=r["doc"];fields,pars=make_fields(source[doc]);refs=gold[q];types=sorted(set(x["type"] for x in refs))
        assert doc not in unique_ids;unique_ids.add(doc)
        row={"q":q,"doc":doc,"type":types[0] if len(types)==1 else "mixed","types":types,"references":len(refs),"arms":{}}
        supported,ceiling=coverage(pars,[[f,0,len(s)] for f,s in fields.items()],refs)
        row["available_coverage_ceiling"]=ceiling
        for arm in ARMS:
            a=r["arms"][arm];p=preds[a["key"]];ans=p.get("answer","")
            active=arm in ("old","edge")
            if active:
                pick=r["anchors"]["right_edge" if arm=="edge" else "same_window"]
                paid=paid_open(wp,fields[pick[0]],*pick)[3] if pick else 0
            else:paid=0
            touched,cov=coverage(pars,r["base"]+a["opened"],refs)
            all_preds[arm][q]=dict(answer=ans,evidence=touched)
            fs=[off.token_f1_score(ans,z["answer"]) if p["ok"] else 0 for z in refs]
            xs=[int(off.normalize_answer(ans)==off.normalize_answer(z["answer"])) if p["ok"] else 0 for z in refs]
            es=[off.paragraph_f1_score(touched,z["evidence"]) for z in refs]
            target=refs[fs.index(max(fs))]["type"]
            row["arms"][arm]=dict(f1=max(fs),em=max(xs),answer_best_type=target,
                predicted_unanswerable=int(off.normalize_answer(ans)=="unanswerable"),paragraph_f1=max(es),
                coverage=cov,complete=int(cov>=1-1e-12) if cov is not None else None,wp_delivered=a["wp_extra"],
                wp_source_read=paid,wp_user=a["wp_user"],qwen_user=a["qwen_user"],model_prompt=p.get("prompt_tokens"),
                model_output=p.get("completion_tokens"),ok=p["ok"],truncated=p.get("finish")=="length",receipt=a["key"])
        outcome[q]=row
    rows=list(outcome.values());assert len(rows)==len(unique_ids)==24
    for r in rows:
        sizes={r["arms"][k]["model_prompt"] for k in ("replay","old","edge") if r["arms"][k]["ok"]}
        r["max_prompt_diff"]=max(sizes)-min(sizes) if sizes else None
    totals={};counts=Counter(r["type"] for r in rows);held={q:gold[q] for q in ctx}
    for k in ARMS:
        official=off.evaluate(held,all_preds[k]);a=[r["arms"][k] for r in rows]
        assert abs(official["Answer F1"]-np.mean([i["f1"] for i in a]))<1e-10
        assert abs(official["Evidence F1"]-np.mean([i["paragraph_f1"] for i in a]))<1e-10
        total={field:avg([i[field] for i in a if i[field] is not None]) for field in
               ("f1","em","paragraph_f1","coverage","complete","predicted_unanswerable","wp_delivered","wp_source_read","wp_user","qwen_user","model_prompt","model_output")}
        total.update(n=len(a),success=sum(i["ok"] for i in a),truncated=sum(i["truncated"] for i in a),nonempty_reference_evidence=sum(i["coverage"] is not None for i in a),
           official=official,unanimous_or_mixed={typ:{"n":n,"f1":avg([r["arms"][k]["f1"] for r in rows if r["type"]==typ]),
              "em":avg([r["arms"][k]["em"] for r in rows if r["type"]==typ])} for typ,n in counts.items()})
        totals[k]=total
    contrasts={}
    for lhs,rhs in (("edge","old"),("edge","replay"),("edge","base"),("old","base"),("replay","base")):
        contrasts[lhs+"-"+rhs]={}
        for field in ("f1","em","coverage","complete","paragraph_f1"):
            v=[r["arms"][lhs][field]-r["arms"][rhs][field] for r in rows if r["arms"][lhs][field] is not None]
            z=estimate(v,field)
            if field=="em":z["mcnemar_exact_two_sided"]=float(binomtest(z["wins"],z["wins"]+z["losses"]).pvalue) if z["wins"]+z["losses"] else 1.
            contrasts[lhs+"-"+rhs][field]=z
    ceiling={field:avg([x for r in rows if (x:=r["available_coverage_ceiling"]) is not None]) for field in ["whole_paper_char_coverage"]}
    ceiling["whole_paper_full_count"]=sum(r["available_coverage_ceiling"] is not None and r["available_coverage_ceiling"]>=1-1e-12 for r in rows)
    ceiling["either_read_f1_oracle"]=avg([max(r["arms"][k]["f1"] for k in ("old","edge")) for r in rows])
    ceiling["either_read_coverage_oracle"]=avg([max(r["arms"][k]["coverage"] for k in ("old","edge")) for r in rows if r["arms"]["old"]["coverage"] is not None])
    write(D/"per-question.json.gz",outcome)
    write(D/"results.json",dict(n=len(rows),all_test_questions=n_all,all_documents=len(source),reader_unique=len(preds),fixed_type_counts=counts,
             aggregate=totals,contrasts=contrasts,ceilings=ceiling,pairs_with_native_difference=sum(bool(r["max_prompt_diff"]) for r in rows),
             max_native_difference=max((r["max_prompt_diff"] or 0) for r in rows),same_old_edge_inputs=sum(r["arms"]["old"]["receipt"]==r["arms"]["edge"]["receipt"] for r in rows),
             forecast_seal=sha(D/"forecast-seal.json"),per_question=sha(D/"per-question.json.gz"),code=sha(Path(__file__))))
    print(json.dumps({k:totals[k]["f1"] for k in ARMS}),contrasts["edge-old"]["f1"])
if __name__=="__main__":main()

"""Score only after completion of the independent per-query forecast seal."""
from common import *
from collections import Counter,defaultdict
from math import erfc,fsum,sqrt
from statistics import fmean,NormalDist
from predict import ARMS,BUDGET

def union(raw):
    result=[]
    for doc,a,b in sorted(set(tuple(span) for span in raw)):
        assert b>a
        if result and result[-1][0]==doc and a<=result[-1][2]:
            result[-1][2]=max(result[-1][2],b)
        else:
            result.append([doc,a,b])
    return result

def overlap(spans,selected):
    return sum(max(0,min(b,y)-max(a,x)) for doc,a,b in spans for d,x,y in selected if doc==d)

def labels(view):
    ids={s[0]:i for i,s in enumerate(view["documents"])}
    docs=source("doc")["doc_data"]
    goals={};issues=Counter();all_q={r[0] for r in view["q"]}
    for domain,dialogs in source("dial_validation")["dial_data"].items():
        for dialog in dialogs:
            did=dialog["dial_id"]
            for turn in dialog["turns"]:
                qid=short(did+"\x1f"+str(turn["turn_id"]))
                if qid not in all_q:continue
                assert qid not in goals and turn["role"]=="agent"
                refs=turn["references"]
                spans=set();issue=None
                for r in refs:
                    doc=r["doc_id"]
                    native=docs.get(domain,{}).get(doc,{})
                    sp=native.get("spans",{}).get(str(r["id_sp"]))
                    if not sp:issue="unresolved_doc_or_span";break
                    i=ids[short(domain+"\x1f"+doc)]
                    body=view["documents"][i][2]
                    a,b=sp["start_sp"],sp["end_sp"]
                    if not (0<=a<b<=len(body)) or body[a:b]!=sp["text_sp"]:
                        issue="source_interval_or_verbatim_mismatch";break
                    spans.add((i,a,b))
                if not refs:issue="empty_reference"
                if issue:issues[issue]+=1
                goals[qid]=(sorted(spans) if not issue else [],issue)
    assert len(goals)==len(all_q)
    return goals,dict(issues)

def inference(rows,field):
    records=[]
    for ref in ("whole","fine"):
        diffs=[r["arms"]["two_ratio"]["full_support"]-r["arms"][ref]["full_support"] for r in rows]
        n=len(diffs);avg=fmean(diffs);group=defaultdict(list)
        for r,x in zip(rows,diffs):
            group[r[field]].append(x-avg)
        g=len(group)
        se=sqrt(g/(g-1)*fsum(fsum(x)**2 for x in group.values()))/n
        z=avg/se if se else (0 if avg==0 else float("inf"))
        p=erfc(abs(z)/sqrt(2))
        records.append(dict(reference=ref,n=n,clusters=g,delta_pp=100*avg,se_pp=100*se,p=p,
                 ci95_pp=[100*(avg+s*NormalDist().inv_cdf(.975)*se) for s in (-1,1)],
                 simultaneous_bonf95_pp=[100*(avg+s*NormalDist().inv_cdf(.9875)*se) for s in (-1,1)],
                 wins=sum(x>0 for x in diffs),losses=sum(x<0 for x in diffs)))
    p_previous=0
    for j,r in enumerate(sorted(records,key=lambda r:r["p"])):
        r["holm_p"]=max(p_previous,min(1,(2-j)*r["p"]))
        p_previous=r["holm_p"]
    return records

def main():
    seal=read(ROOT/"forecast-seal.json")
    assert checksum(ROOT/"predictions.json.gz")==seal["forecasts"]
    assert checksum(ROOT/"input-lock.json")==seal["input"] and checksum(WEIGHTS)==seal["weights"]
    preds=read(ROOT/"predictions.json.gz")
    view=get_views()
    qset={r[0]:r[1] for r in view["q"]}
    assert len(preds)==len(qset)==661 and {p["q"] for p in preds}==set(qset)
    goals,issues=labels(view)
    t=tok(); units=view["blocks"];docs=view["documents"]
    out=[];excluded={};by_arm=defaultdict(list);seen=[]
    for p in preds:
        q=p["q"];go,issue=goals[q]
        assert p["dialogue"]==qset[q]
        if issue:excluded[q]=issue
        targetdocs={d for d,_,_ in go}
        gold=union(go)
        denom=sum(b-a for _,a,b in gold)
        if not issue:
            row={"q":q,"dialogue":p["dialogue"],"gold_set":";".join(map(str,sorted(targetdocs))),"n_gold_spans":len(go),
                 "n_gold_docs":len(targetdocs),"top1":int(targetdocs<=set(p["top_documents"][:1])),
                 "top5":int(targetdocs<=set(p["top_documents"])),"arms":{}}
        for arm in ARMS:
            a=p["arms"][arm]
            items=[units[i] for i in a["chosen"]]
            rendered="\n".join(render(u,docs) for u in items)
            charge=len(t.encode(rendered,add_special_tokens=False).ids)
            assert charge==a["tokens"]<=BUDGET and sha(rendered.encode())==a["text_sha"]
            selected=union((b["doc"],b["a"],b["b"]) for b in items)
            read_chars=sum(h-l for d,l,h in selected)
            assert read_chars==sum(b["b"]-b["a"] for b in items)
            by_arm[arm].append(charge)
            if issue:continue
            covered=overlap(gold,selected)
            rec=covered/denom
            den=covered/read_chars if read_chars else 0
            row["arms"][arm]=dict(full_support=int(covered==denom),coverage=rec,density=den,
                f1=2*den*rec/(den+rec) if den+rec else 0,all_gold_docs=int(targetdocs<={d for d,_,_ in selected}),
                span_recall=fmean(overlap([s],selected)==s[2]-s[1] for s in go),tokens=charge,
                source_chars=read_chars,selected=len(items))
        if not issue:out.append(row)
    assert len(out)+len(excluded)==661
    summaries={k:{m:fmean(r["arms"][k][m] for r in out) for m in out[0]["arms"][k]} for k in ARMS}
    details=save(ROOT/"per-query-scores.json.gz",dict(rows=out,unscored=excluded))
    result=dict(sampled=661,scored=len(out),excluded=issues,doc_sets=len({r["gold_set"] for r in out}),
                top1_docs=fmean(r["top1"] for r in out),top5_docs=fmean(r["top5"] for r in out),
                metrics=summaries,token_cost_all_queries={k:dict(min=min(v),max=max(v),mean=fmean(v)) for k,v in by_arm.items()},
                document_cardinality_hist=dict(Counter(r["n_gold_docs"] for r in out)),
                all_primary_paired=inference(out,"dialogue"),sensitivity_same_gold_docs=inference(out,"gold_set"),
                per_query=details,seal=checksum(ROOT/"forecast-seal.json"),code=checksum(Path(__file__)))
    print("scored",len(out),issues,"sha",save(ROOT/"results.json",result),flush=True)
    print(result["all_primary_paired"]);print(result["sensitivity_same_gold_docs"])
    for k, values in summaries.items():print(k,values)
if __name__=="__main__":
    main()

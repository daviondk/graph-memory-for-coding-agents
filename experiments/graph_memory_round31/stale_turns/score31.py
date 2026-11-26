"""Trace normalized gold spans back to raw source offsets, score committed forecasts, and build a masked semantic sample."""
import bisect,collections,re,time,unicodedata
from base31 import D,P,W,Path,sha,h,save,read,DATA,refs,data
def tokenize(text):
    pats=list(re.finditer(r"[^\W_]+",text,flags=re.UNICODE))
    return [(unicodedata.normalize("NFKC",m[0]).casefold(),m.start(),m.end()) for m in pats]
def join_source(src):
    text="";turns=[]
    for z in src["turns"]:
        if z["role"].lower()!="user" or not z["text"]:continue
        if text:text+="\n"
        start=len(text);text+=z["text"];turns.append((z["id"],start,len(text)))
    return text,turns
def locate(value,full,turns):
    ws=tokenize(full);gold=[x[0] for x in tokenize(value)]
    if not gold:return []
    n=len(gold);ss=[x[0] for x in ws];locations=[]
    for i,w in enumerate(ss):
        if w!=gold[0] or ss[i:i+n]!=gold:continue
        lo=ws[i][1];hi=ws[i+n-1][2]
        locations.append(dict(span=[lo,hi],word_offsets=[(a,b) for _,a,b in ws[i:i+n]],
                         turns=[tid for tid,a,b in turns if a<hi and b>lo]))
    return locations
def delivered(ref,loc,z):
    if z is None:
        return {"source":False,"full":False,"cov":0.0,"turn":False,"raw_span":None,"matched_words":0,"total_words":ref}
    lo=z["start"];hi=z["end"];best=(0,None);turn=False
    for occ in loc:
        matched=sum(a>=lo and b<=hi for a,b in occ["word_offsets"])
        if best[1] is None or matched>best[0]:best=matched,occ["span"]
        turn=turn or bool(set(occ["turns"])&set(z["turns"]))
    return dict(source=True,full=(ref>0 and best[0]==ref),cov=best[0]/ref if ref else 0.0,turn=turn,raw_span=best[1],matched_words=best[0],total_words=ref)
def pooled(rows):
    n=len(rows);out={}
    for field in ["old_full","new_full","both_full","old_turn","new_turn","both_turn","old_source","new_source","both_source",
                  "old_cov","new_cov","both_mean_cov","tokens","bytes"]:
        out[field]=sum(r[field] for r in rows)
    return {"n":n,**out}
def compare(rows):
    from itertools import groupby
    import numpy as np
    indices={};agg={}
    for r in rows:
        key=(r["scope"],r["method"],r["case"],r["q"]);indices[key]=r
    for split in ("test","dev","all"):
        rr=[r for r in rows if split=="all" or r["split"]==split]
        scopes=sorted(set(r["scope"] for r in rr));cases=sorted(set(r["case"] for r in rr))
        questions={c:sorted({r["q"] for r in rr if r["case"]==c}) for c in cases}
        for scope in scopes:
            for base in ["win_hybrid","turn_ensemble","turn_bm","turn_e5","turn_hybrid","turn_late","win_bm","first","last"]:
                rg=np.random.default_rng(310257);sam=rg.integers(0,len(cases),(10000,len(cases)),dtype="int16")
                for field in ["both_full","both_mean_cov","both_turn","new_full"]:
                    dd=[];win=loss=tie=0
                    for c in cases:
                        ds=[float(indices[scope,"turn_pair",c,q][field])-float(indices[scope,base,c,q][field]) for q in questions[c]]
                        dd.append(sum(ds)/len(ds));win+=sum(x>0 for x in ds);loss+=sum(x<0 for x in ds);tie+=sum(x==0 for x in ds)
                    d=np.array(dd);boots=d[sam].mean(axis=1)
                    qs=[.0125,.9875] if scope=="known" and base in ("win_hybrid","turn_ensemble") and field=="both_full" and split=="test" else [.025,.975]
                    agg["/".join([split,scope,base,field])]=dict(n_cases=len(cases),n_questions=win+loss+tie,delta=float(d.mean()),
                              interval=np.quantile(boots,qs).tolist(),coverage=1-2*qs[0],wins=win,losses=loss,ties=tie)
    return agg
def main():
    seal=read(D/"forecast-seal.json");af=D/"access.json.gz";ff=D/"forecast.json.gz";assert sha(af)==seal["access"] and sha(ff)==seal["forecast"]
    access=read(af);pred=read(ff);split=read(D/"case-split.json");lock=refs();lf=DATA/"evaluator/labels.json.gz";assert sha(lf)==lock["labels_sha"]
    ps=read(D/"position-seal.json");pf=D/"position-forecast.json.gz";assert sha(pf)==ps["output"] and ps["forecast"]==sha(D/"forecast-seal.json")
    for k,v in read(pf).items():pred[k].update(v)
    labels=read(lf);by=collections.defaultdict(list)
    for r in labels:by[r["case"]].append(r)
    rows=[];limits={};refsout={};frame_pool={};budget=collections.Counter()
    for c,rs in sorted(by.items()):
        hh={s["id"]:join_source(s) for s in read(DATA/"history"/(c+".json.gz"))["sources"]}
        zref=rs[0];facts={}
        assert all(all(r[k]==zref[k] for k in ("old","new","old_source","new_source")) for r in rs)
        for side in ("old","new"):
            sid=zref[side+"_source"];fact=zref[side]
            txt,turns=hh[sid];loc=locate(fact,txt,turns)
            facts[side]=(sid,loc,len(tokenize(fact)));refsout[c+"/"+side]={"source":sid,"words":len(tokenize(fact)),
               "locations":[{"span":z["span"],"turns":z["turns"]} for z in loc],"text_sha":h(fact)}
        for r in rs:
            q=r["qid"]
            for tag,k in access[q].items():
                outputs=pred[k];native=[];addresses=[]
                for method,frames in outputs.items():
                    ids=[z["source"] for z in frames];received={z["source"]:z for z in frames};fields={}
                    for side,(sid,loc,n) in facts.items():
                        adj=delivered(n,loc,received.get(sid));fields.update({side+"_"+sk:adj[sk] for sk in ["source","full","cov","turn","matched_words","total_words"]})
                        if split[c]=="test":
                            for frame in frames:
                                correct_source=frame["source"]==sid
                                which=adj if correct_source else delivered(n,loc,None)
                                bucket="full" if which["full"] else ("partial" if which["cov"]>0 else ("zero_true" if correct_source else "zero_other"))
                                distinct=h(c+side+frame["frame_hash"])
                                if distinct not in frame_pool:
                                    frame_pool[distinct]=dict(case=c,evidence_source=frame["source"],evidence_start=frame["start"],evidence_end=frame["end"],
                                     target_side=side,bucket=bucket,q=q,method=method,scope=tag,score=which["cov"],target_text=zref[side],
                                     text=hh[frame["source"]][0][frame["start"]:frame["end"]])
                    for attr in ("full","turn","source"):fields["both_"+attr]=fields["old_"+attr] and fields["new_"+attr]
                    fields["both_mean_cov"]=(fields["old_cov"]+fields["new_cov"])/2
                    ns=sum(z["native"] for z in frames);bs=sum(z["utf8_bytes"] for z in frames);native.append(ns);addresses.append(ids)
                    rows.append(dict(case=c,q=q,split=split[c],scope=tag,method=method,dimension=r["dimension"],scenario_type=r["scenario_type"],tokens=ns,bytes=bs,**fields))
                assert len(set(native))==1 and all(x==addresses[0] for x in addresses)
                budget[tag]+=native[0]
    assert len(rows)==400*3*2*10 and len(access)==1200 and len(by)==400
    # Each example uses a different held-out case. No policy or literal-coverage annotation appears in a reviewer's view.
    selected=[];used=set()
    for bucket,n in [("full",8),("partial",8),("zero_true",4),("zero_other",4)]:
        cand=sorted((k for k,v in frame_pool.items() if v["bucket"]==bucket),key=lambda k:h("r31-calibration/"+k))
        ss=[]
        for k in cand:
            v=frame_pool[k]
            if v["case"] in used:continue
            used.add(v["case"]);ss.append((k,v))
            if len(ss)==n:break
        assert len(ss)==n;selected.extend(ss)
    selected.sort(key=lambda t:h("r31-blind-order/"+t[0]));packet=[];reviewmap={}
    for k,v in selected:
        key=h("r31-review/"+k)[:20];packet.append(dict(id=key,claim=v["target_text"],excerpt=v["text"]))
        reviewmap[key]={a:b for a,b in v.items() if a not in ("target_text","text")}
    save(P/"review-packet.json",packet);save(P/"review-map.json",reviewmap)
    save(D/"score-rows.json.gz",rows);save(D/"gold-spans.json.gz",refsout)
    groups=collections.defaultdict(list)
    for r in rows:
        for g in ("all",r["split"],r["split"]+"-"+r["dimension"],r["split"]+"-"+r["scenario_type"]):groups["/".join((g,r["scope"],r["method"]))].append(r)
    save(D/"score.json",dict(forecast_seal=sha(D/"forecast-seal.json"),code=sha(Path(__file__)),position_seal=sha(D/"position-seal.json"),rows=sha(D/"score-rows.json.gz"),
         gold=sha(D/"gold-spans.json.gz"),summary={k:pooled(rr) for k,rr in groups.items()},contrasts=compare(rows),
        exact_reference_coverage={side:sum(bool(v["locations"]) for k,v in refsout.items() if k.endswith("/"+side)) for side in ("old","new")},
        native_budget=budget,review_packet=sha(P/"review-packet.json"),review_map=sha(P/"review-map.json")))
if __name__=="__main__":main()

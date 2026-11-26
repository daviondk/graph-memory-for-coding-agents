"""Address- and byte-level evaluation on actual deliveries, with fixed repository-only receiver targets."""
from collections import Counter,defaultdict
from statistics import mean
import numpy as np
from tokenizers import Tokenizer
from extract import strict
from source import D,P,get,save,sha,h,pq,cohort
from pathlib import Path
T=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json")
VIEWS=("repo_only","raw_trace","summary_notes","structured_notes");CUSTOM=("bm25","recent","repeated","rrf2","rrf3")
FIELDS=("pair","fraction","text_pair","text_fraction","tokens","bytes")
def group(selected):
    by=defaultdict(list)
    for r in selected:by[r["issue"]].append(r)
    return by
def summary(rows):
    issues=group(rows);names=rows[0]["arms"];draw=np.random.default_rng(31031).integers(0,len(issues),(10000,len(issues)))
    table={a:np.array([np.mean([r["arms"][a] for r in items],axis=0) for issue,items in sorted(issues.items())]) for a in names}
    methods={a:{k:float(v) for k,v in zip(FIELDS,m.mean(0))} for a,m in table.items()};pairs={}
    for a,b in [("rrf3","rrf2"),("rrf3","bm25"),("rrf3","recent"),("raw_trace","structured_notes"),("raw_trace","summary_notes"),("rrf3","raw_trace")]:
        ds=table[a]-table[b];vals=ds[draw].mean(1);pairs[a+"__"+b]={k:{"delta":float(ds[:,i].mean()),"ci":np.quantile(vals[:,i],[.025,.975]).tolist(),"win":int((ds[:,i]>1e-12).sum()),"loss":int((ds[:,i]<-1e-12).sum())} for i,k in enumerate(FIELDS)}
    return dict(groups=len(rows),issues=len(issues),cp=len({r["cp"] for r in rows}),methods=methods,paired=pairs,original_pair=sum(r["available_pair"] for r in rows),candidate_receipts=sum(r["available_count"] for r in rows))
def main():
    seal=get(D/"forecast-seal.json");assert sha(P/"packets.json.gz")==seal["packets"] and sha(P/"prefix.json.gz")==seal["inputs"]
    packets={r["cp"]:r for r in get(P/"packets.json.gz")};sections=get(P/"sections.json.gz");meta=get(D/"delivery-metadata.json.gz");target={r["q"]:r for r in get(P/"targets.json.gz")}
    t=Tokenizer.from_file(str(T));t.no_truncation()
    note_info={};groups=defaultdict(dict);states=Counter();native=[]
    for row in meta:
        q=row["q"];a=row["view"];g=row["group"];assert a not in groups[g];groups[g][a]=row
        text=sections[q];hx=h(text)
        if hx not in note_info:note_info[hx]=(strict(text),len(t.encode(text,add_special_tokens=False).ids),len(text.encode()))
    def native_score(row,keys,texts,exists):
        sec=sections[row["q"]];idx,tc,nb=note_info[h(sec)]
        exact=[e and k in idx for k,e in zip(keys,exists)]
        quote=[e and s in sec for s,e in zip(texts,exists)]
        return [int(all(exact)),mean(exact),int(all(quote)),mean(quote),tc,nb]
    def material(receipt,tar):
        path,lo,hi=tar;keys=[(path,z[0],h(z[1])) for z in (lo,hi)];texts=[lo[1],hi[1]];catalog=set(map(tuple,receipt["keys"]));exists=[k in catalog for k in keys]
        return keys,texts,exists
    for row in meta:
        q=row["q"];out=target[q];sub=row["subset"];a=row["view"];reason=out["reason"];states[sub,a,reason]+=1
        if not out["target"]:continue
        receipt=packets[row["cp"]];keys,texts,exists=material(receipt,out["target"])
        arm=native_score(row,keys,texts,exists)
        native.append(dict(q=q,cp=row["cp"],issue=row["issue"],group=row["group"],subset=sub,view=a,available_pair=all(exists),available_count=sum(exists),values=arm))
    fixed=[];flow=Counter()
    for g,views in groups.items():
        if "repo_only" not in views:continue
        row=views["repo_only"];cp=row["cp"];sub=row["subset"];flow[sub,"all_groups"]+=1
        if set(views)!=set(VIEWS):flow[sub,"missing_views"]+=1;continue
        for v in views.values():assert all(v[k]==row[k] for k in ("cp","subset","group","issue"))
        flow[sub,"all_four_verified"]+=1;truth=target[row["q"]];flow[sub,truth["reason"]]+=1
        if not truth["target"]:continue
        receipt=packets[cp];keys,texts,exists=material(receipt,truth["target"]);arms={v:native_score(r,keys,texts,exists) for v,r in views.items()}
        for a,c in receipt["controls"].items():
            ids=set(map(tuple,c["index"]));ok=[k in ids for k in keys];pieces={k[2] for k in ids};quotes=[k[2] in pieces and e for k,e in zip(keys,exists)]
            arms[a]=[int(all(ok)),mean(ok),int(all(quotes)),mean(quotes),c["tokens"],c["bytes"]]
        fixed.append(dict(cp=cp,group=g,subset=sub,issue=row["issue"],available_pair=all(exists),available_count=sum(exists),arms=arms))
    results={};natural={}
    for sub in sorted({r["subset"] for r in meta}):
        subset=[r for r in fixed if r["subset"]==sub];eligible=[r for r in subset if r["available_pair"]]
        results[sub]=dict(all=summary(subset) if subset else None,visible=summary(eligible) if eligible else None)
        natural[sub]={}
        for a in VIEWS:
            sel=[r for r in native if r["subset"]==sub and r["view"]==a];issues=group(sel)
            if not sel:continue
            one=np.array([np.mean([r["values"] for r in rs],axis=0) for rs in issues.values()])
            natural[sub][a]=dict(groups=len(sel),issues=len(issues),initially_visible=sum(r["available_pair"] for r in sel),method=dict(zip(FIELDS,one.mean(0).tolist())))
    js=lambda v:{"|".join(k):n for k,n in v.items()}
    rec=dict(fixed=results,natural=natural,raw_flow=js(states),matched_flow=js(flow),native_views=list(VIEWS),fields=FIELDS,fixed_receipt=save(D/"fixed-outcomes.json.gz",fixed),natural_receipt=save(D/"natural-outcomes.json.gz",native));save(D/"results.json",rec)
    for s,tbl in results.items():
        if not tbl["all"]:continue
        u=tbl["all"];print(s,u["groups"],u["issues"],u["original_pair"],{a:round(r["pair"],4) for a,r in u["methods"].items()},u["paired"]["rrf3__rrf2"]["pair"])
if __name__=="__main__":main()


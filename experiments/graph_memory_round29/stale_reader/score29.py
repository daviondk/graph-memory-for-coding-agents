"""Evaluate frozen answers. References and reviewer mapping only enter after the responses are sealed."""
import collections,itertools,random,statistics,unicodedata,re
from setup29 import D,P,h,sha,read,save,Path
DIMS=["dim1_query","dim2_query","dim3_query"]
PAST=["past_prefix","past_full"]
ARMS=["H","T","G","O"]
def norm(text):
    text=unicodedata.normalize("NFKC",text).casefold()
    return " ".join(re.findall(r"[^\W_]+",text))
def present(utterance,texts):
    u=norm(utterance)
    return bool(u) and any((" "+u+" ") in (" "+norm(t)+" ") for t in texts)
def stat(rows):
    a={}
    for k in ("old_source","new_source","both_sources","old_literal","new_literal","both_literal"):
        xs=[r[k] for r in rows if r.get(k) is not None]
        a[k]=sum(xs) if xs else None
    a["n"]=len(rows)
    a["approved"]=sum(r["grade"] in ("1","V") for r in rows) if rows and all("grade" in r for r in rows) else None
    a["grades"]=dict(collections.Counter(r["grade"] for r in rows if "grade" in r))
    return a
def paired(rows,pair,field,modes):
    a,b=pair
    cells=collections.defaultdict(dict)
    for r in rows:
        if r["mode"] in modes and r["arm"] in pair:cells[r["case"]][r["mode"],r["arm"]]=float(r[field])
    d=[];w=l=t=0
    for c,g in sorted(cells.items()):
        ds=[g[m,a]-g[m,b] for m in modes];d.append(statistics.mean(ds))
        w+=sum(x>0 for x in ds);l+=sum(x<0 for x in ds);t+=sum(x==0 for x in ds)
    rng=random.Random(290327)
    boots=sorted(statistics.mean(rng.choices(d,k=len(d))) for _ in range(20000))
    extreme=sum(abs(sum(v*s for v,s in zip(d,sg)))>=abs(sum(d))-1e-10 for sg in itertools.product((-1,1),repeat=len(d)))
    return {"delta":statistics.mean(d),"case_sign_flip_p_two_sided":extreme/(2**len(d)),"bootstrap95": [boots[499],boots[19499]],"wins":w,"losses":l,"ties":t,"case_deltas":d}
def main():
    ef=read(D/"effective-actor-forecast-seal.json");jf=read(D/"judge-forecast-seal.json");se=read(D/"input-seal.json")
    assert sha(P/"effective-actor-outputs.json.gz")==ef["raw"] and sha(P/"judge-outputs.json.gz")==jf["raw"]
    assert sha(P/"eval-keys.json.gz")==se["eval_keys"]
    ans=read(P/"effective-actor-outputs.json.gz");aes=read(D/"effective-actor-assignment.json.gz");jg=read(P/"judge-outputs.json.gz")
    jas=read(D/"judge-assignment.json.gz");keys=read(P/"eval-keys.json.gz");rr=read(D/"effective-retrieval.json.gz")
    clips=read(P/"effective-strings.json.gz");hs=read(P/"reader-histories.json.gz");ss=read(P/"reader-questions.json");oracle=read(P/"oracle.json.gz")
    src={v["id"]:v for hist in hs.values() for v in hist}
    rows=[];budget={};literal_coverage={}
    for q,z in sorted(keys.items()):
        k=z["case"];mode=z["mode"];hist=mode in PAST;budget[q]={}
        if k not in literal_coverage:
            literal_coverage[k]={side:present(z[side],[u["text"] for u in src[z[side+"_source"]]["turns"] if u["role"].lower()=="user"]) for side in ("old","new")}
        for arm in [*ARMS,"B"]:
            if arm=="O":
                ls=oracle[q];source_ids=set();texts=[text for ts,text in ls]
            else:
                ls=rr[q][arm];source_ids={r["source"] for r in ls}
                if arm=="B":
                    def evidence_excerpt(v):
                        joined="\n".join(t["text"] for t in src[v["source"]]["turns"] if t["role"].lower()=="user")
                        return joined[v["origin"]:v["end"]]
                    texts=[evidence_excerpt(v) for v in ls]
                else:texts=[v["text"].split("] ",1)[1] for v in clips[q][arm]]
            old_hit=z["old_source"] in source_ids;new_hit=z["new_source"] in source_ids
            ol=present(z["old"],texts);nl=present(z["new"],texts)
            item=dict(q=q,case=k,mode=mode,scenario_type=z["type"],arm=arm,
                  old_source=old_hit if arm!="O" else None,new_source=new_hit if arm!="O" else None,
                  both_sources=old_hit and new_hit if arm!="O" else None,old_literal=ol if arm!="B" else None,new_literal=nl if arm!="B" else None,both_literal=ol and nl if arm!="B" else None)
            if arm!="B":
                ai=aes[q][arm];jkey,idx=jas[q+"/"+arm];result=ans[ai];assert result["ok"] and jg[jkey]["ok"]
                grade=jg[jkey]["answer"][idx]
                item.update(grade=grade,pass_proxy=grade in ("1","V"),answer_sha=h(result["answer"]),request_sha=ai,judge_request=jkey,
                         input_tokens=result["prompt_tokens"],output_tokens=result["completion_tokens"],finish_reason=result["finish"],
                         actor_request_seconds=sum(z["s"] for z in result["tries"]),false_retroactive=grade=="R" if hist else None)
                if arm in ("H","T","G"):
                    budget[q][arm]=dict(full=result["prompt_tokens"],slots=[v["n"] for v in clips[q][arm]])
            rows.append(item)
    assert len(rows)==200
    costs={}
    for arm in ARMS:
        x=[r for r in rows if r["arm"]==arm];cs=[r["input_tokens"] for r in x]
        costs[arm]=dict(n=len(x),input_sum=sum(cs),input_min=min(cs),input_max=max(cs),output_sum=sum(r["output_tokens"] for r in x),
             capped=sum(r["finish_reason"]=="length" for r in x),logical_request_seconds=round(sum(r["actor_request_seconds"] for r in x),2))
    budgetdiff=[max(x["full"] for x in v.values())-min(x["full"] for x in v.values()) for v in budget.values()]
    assert all(len(set(tuple(a["slots"]) for a in v.values()))==1 for v in budget.values())
    arms=[*ARMS,"B"];out={}
    for m,modes in [("native",DIMS),("historical",PAST),*((z,[z]) for z in DIMS+PAST)]:
        out[m]={a:stat([r for r in rows if r["mode"] in modes and r["arm"]==a]) for a in arms}
    typ={}
    cases={c["scenario_type"] for c in rows}
    for t in sorted(cases):typ[t]={a:stat([r for r in rows if r["mode"] in DIMS and r["arm"]==a and r["scenario_type"]==t]) for a in arms}
    pairout={}
    for pair in [("G","T"),("G","H"),("T","H")]:
        lab="-".join(pair);pairout[lab]={}
        for m,modes in [("native",DIMS),("historical",PAST),*((z,[z]) for z in PAST)]:
            fields=["pass_proxy","old_source","new_source","both_sources"]+(["false_retroactive"] if m!="native" else [])
            pairout[lab][m]={f:paired(rows,pair,f,modes) for f in fields}
    save(D/"score-rows.json.gz",rows);save(D/"score.json",dict(source=sha(D/"input-seal.json"),effective=sha(D/"effective-actor-forecast-seal.json"),
         judge=sha(D/"judge-forecast-seal.json"),per_row=sha(D/"score-rows.json.gz"),code=sha(Path(__file__)),scores=out,strata=typ,
         paired=pairout,costs=costs,literal_whole_source=literal_coverage,slot_unequal=0,full_cost_max_difference=max(budgetdiff),
         full_cost_spread_counts=dict(collections.Counter(budgetdiff)),unique_prompt_costs={k:sum(a[k] for a in ans.values()) for k in ["prompt_tokens","completion_tokens"]},
         unique_judge_costs={k:sum(a[k] for a in jg.values()) for k in ["prompt_tokens","completion_tokens"]}))
if __name__=="__main__":main()

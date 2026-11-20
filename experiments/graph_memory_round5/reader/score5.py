"""Re-open references only when the response set for each experiment is complete."""
from collections import Counter,defaultdict
from functools import lru_cache
from math import comb
from pathlib import Path
import sys, gzip, json, re
import numpy as np
from infer import D, sha, save, read
P=D.parents[1]/"graph_memory_round4/repo"
sys.path.insert(0,str(P))
from data_io import rows

def line(s):
    return next((t for v in s.splitlines() if (t:=v.strip()) and not t.startswith(chr(96)*3)),"")
def similarity(a,b):
    if a==b:return 100
    prev=[0]*(len(b)+1)
    for x in a:
        nxt=[0]
        for j,y in enumerate(b):
            nxt.append(prev[j]+1 if x==y else max(nxt[-1],prev[j+1]))
        prev=nxt
    return round(200*prev[-1]/(len(a)+len(b)))
ident=re.compile(r"[A-Za-z_$][\w$]*")
def f1(a,b):
    x=set(ident.findall(a));y=set(ident.findall(b))
    return 2*len(x&y)/(len(x)+len(y)) if x or y else 1.
@lru_cache(None)
def sealed(k):
    ix=read(k+"_assignment.json");lock=read(k+"_decisions.json");inputs=read(k+"_input_lock.json")
    for n,h in inputs.items():assert sha((D/n).read_bytes())==h,n
    assert {s+".json.gz" for v in ix.values() for s in v.values()}==set(lock)
    for n,h in lock.items():assert sha((D/(k+"_calls")/n).read_bytes())==h,n
    return ix
@lru_cache(None)
def get(k,h):
    rec=read(k+"_calls/"+h+".json.gz")
    return rec["reply"],rec["elapsed"]
def metrics_per_row(k,row,ref,goldidx):
    methods={};ix=sealed(k)[row["id"]]
    for a,(snippet,sn) in row["snippets"].items():
        h=ix[a];reply,elapsed=get(k,h);ans=line(reply["choices"][0]["message"]["content"] or "")
        addr=row.get("addresses",{}).get(a,row["rank"][0] if a!="empty" else -1)
        hits=(row["rank"][:4] if a in ("portfolio","four_head") else [addr])
        methods[a]=dict(line=ans,em=int(ans==ref),es=similarity(ans,ref),id_f1=f1(ans,ref),hit=int(goldidx in hits),
                        external_copy=int(ref in [s.strip() for s in snippet.splitlines()]) if a!="empty" else 0,
                        snippet_tokens=sn,prompt_tokens=reply["usage"]["prompt_tokens"],reply_tokens=reply["usage"]["completion_tokens"],
                        time=elapsed,finish=reply["choices"][0]["finish_reason"],call=h,addr=addr)
    return methods
def exact(w,l):
    n=w+l
    return min(1.,2*sum(comb(n,i) for i in range(min(w,l)+1))/2**n) if n else 1.
def compare(items,a,b,metric):
    diffs=np.array([row["methods"][a][metric]-row["methods"][b][metric] for row in items],dtype=float)
    rng=np.random.default_rng(18052026)
    sims=diffs[rng.integers(len(diffs),size=(10000,len(diffs)))].mean(axis=1)
    w=int((diffs>0).sum());l=int((diffs<0).sum())
    return dict(diff=float(diffs.mean()),ci=np.quantile(sims,[.025,.975]).tolist(),wins=w,losses=l,p=exact(w,l) if metric in ("em","hit") else None)
from original_targets import gold_rows
def main(k):
    sealed(k); info=read(k+"_packets.json.gz");base={}
    if k=="C":
        sealed("C0");base={r["id"]:r for r in read("C0_packets.json.gz")}
    loc=defaultdict(dict);out=[]
    for x in info:loc[x["file"]][x["local_index"]]=x
    for fname,indices in loc.items():
        for i,r in enumerate(gold_rows(P/"archive_inputs"/fname)):
            if i not in indices:continue
            x=indices[i];ref=r["next_line"].strip();goldidx=r["gold_snippet_index"]
            m=metrics_per_row(k,x,ref,goldidx)
            if base:m.update(metrics_per_row("C0",base[x["id"]],ref,goldidx))
            out.append(dict(id=x["id"],repo=x["repo"],panel=x["panel"],methods=m,gold=ref,gold_index=goldidx,
                            ctx_copy=int(ref in [s.strip() for s in x["ctx"].splitlines()]),edge=x.get("edge_event") is not None,reason=x.get("reason","")))
    assert len(out)==len(info)==len({x["repo"] for x in out})
    arms=list(out[0]["methods"]);pairs=([("edge","local"),("local","head")] if k!="C" else [("verified","draft_lex"),("verified","static_focus"),("verified","head"),("draft_lex","static_focus"),("static_focus","head"),("verified","empty")])
    if k=="A":pairs += [("portfolio","four_head"),("portfolio","head"),("head","empty"),("edge","empty")]
    def sub(items):
        m={a:{f:float(np.mean([x["methods"][a][f] for x in items])) for f in ("em","es","id_f1","hit","snippet_tokens","prompt_tokens","reply_tokens","time","external_copy")} for a in arms}
        for a in arms:
            m[a]["correct"]=sum(x["methods"][a]["em"] for x in items)
            m[a]["hit_n"]=sum(x["methods"][a]["hit"] for x in items)
            m[a]["finished"]=dict(Counter(x["methods"][a]["finish"] for x in items))
        cm={a+"-"+b:{f:compare(items,a,b,f) for f in ("em","es","id_f1","hit")} for a,b in pairs}
        return dict(n=len(items),methods=m,contrasts=cm)
    used={(k,a) for v in sealed(k).values() for a in v.values()}
    if base:used.update(("C0",a) for v in sealed("C0").values() for a in v.values())
    total={field:sum(get(j,h)[0]["usage"][field] for j,h in used) for field in ("prompt_tokens","completion_tokens")}
    result={"all":sub(out),"strata":{s:sub([x for x in out if x["panel"]==s]) for s in sorted({x["panel"] for x in out})},"physical_calls":len(used),"tokens":total,"project_count":len(out)}
    if base:
        result["reason"]=dict(Counter(i["reason"] for i in out));result["reroutes"]={a:sum(x["methods"][a]["addr"]!=x["methods"]["head"]["addr"] for x in out) for a in ("verified","draft_lex")}
    else:
        changed=[i for i in out if i["methods"]["edge"]["call"]!=i["methods"]["local"]["call"]]
        result["actual_change_n"]=len(changed);result["actual_change"]=sub(changed) if changed else None
    save(k+"_items.json.gz",out);save(k+"_results.json",result)
    print(k,len(out),len(used),[(a,result["all"]["methods"][a]["correct"]) for a in arms],flush=True)
def holm():
    p={k:read(k+"_results.json")["all"]["contrasts"]["edge-local"]["em"]["p"] for k in "AB"}
    lo,hi=sorted(p,key=p.get);v=min(1.,2*p[lo])
    save("AB_adjusted.json",dict(raw=p,adjusted={lo:v,hi:max(v,p[hi])},family="A and B exact McNemar, two-sided, Holm adjustment"))
if __name__=="__main__":holm() if sys.argv[1]=="holm" else main(sys.argv[1])


"""Independent replay audit of persistence experiments. Writes only this script's JSON receipt."""
import sys,re,gzip,json,hashlib,itertools
from collections import Counter,defaultdict
from pathlib import Path
from functools import lru_cache
import numpy as np
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D))
import optimal
import replay
sys.path.insert(0,str(D.parent/"repo/lib"))
from tokenizers import Tokenizer
PACK=D.parents[1]/"memory_session5/packets"
TOK=Tokenizer.from_file(str(PACK/"qwen_tokenizer.json"))
def get(p):return json.loads(p.read_bytes())
def read(p):
    with gzip.open(p,"rt",encoding="utf8") as f:
        for line in f:yield json.loads(line)
def h(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
@lru_cache(10000)
def price(s):return len(TOK.encode(s,add_special_tokens=False).ids)
def render(rec):
    p,a,b,body=rec
    return f"@@ {p} {a}..{b} @@\n"+body
def index(rec):
    f,lo,hi,txt=rec;ls=txt.split("\n");assert len(ls)==hi-lo+1
    return [((f,lo+j),s) for j,s in enumerate(ls)]
def goal(events,t):
    for name,a,response in events[t:t+4]:
        if a.get('command')!='str_replace':continue
        p=a.get('path');txt=a.get('old_str')
        if not isinstance(p,str) or not isinstance(txt,str) or not txt:continue
        p=p.removeprefix('/testbed/').removeprefix('./')
        if not p or p.startswith('/') or '..' in p.split('/'):continue
        if re.search(r'(?:The file .*? has been edited\.|successfully replaced)',response[:1300],re.I):return p,txt
        return None
def oracle(catalog,ids,request):
    path,needle=request;data={}
    for j in ids:
        if catalog[j][0]!=path:continue
        data.update(index(catalog[j]))
    coords=sorted(n for p,n in data)
    segments=[]
    for n in coords:
        if not segments or n!=segments[-1][-1]+1:segments.append([])
        segments[-1].append(n)
    candidates=[]
    for segment in segments:
        text="\n".join(data[path,n] for n in segment);start=0
        while (off:=text.find(needle,start))!=-1:
            lo=segment[0]+text.count("\n",0,off);hi=lo+needle.count("\n")
            candidates.append([(n,data[path,n]) for n in range(lo,hi+1)])
            if len(candidates)>1:return []
            start=off+1
    return candidates[0] if candidates else []
def matches(catalog,ids,path,targets):
    resident={k[1]:s for j in ids if catalog[j][0]==path for k,s in index(catalog[j])}
    v=[resident.get(n)==s for n,s in targets]
    return [int(bool(v) and all(v)),sum(v)/len(v) if v else 0.,int(bool(v) and v[0])]
def brute():
    rng=np.random.default_rng(407281);trials=0
    for n in range(1,12):
        for budget_kind in range(14):
            cs=rng.integers(1,13,size=n).tolist();B=0 if budget_kind==0 else (sum(cs)+1 if budget_kind==1 else int(rng.integers(1,sum(cs)+1)))
            w=rng.integers(0,9,size=(n,3)).astype(float)
            for j in range(n):
                if j==0:w[j,1:]=0
                if j==1:w[j,2]=0
            kept,v=optimal.dynamic(cs,w,B)
            def value(mask):
                total=0.
                for i,b in enumerate(mask):
                    if not b:continue
                    for width in (1,2,3):
                        if i-width+1>=0 and all(mask[i-width+1:i+1]):total+=w[i,width-1]
                return total
            best=max(value(mask) for mask in itertools.product((0,1),repeat=n) if sum(c for c,b in zip(cs,mask) if b)<=B)
            assert abs(best-v)<1e-9 and sum(cs[j] for j in kept)<=B and value([j in kept for j in range(n)])==best;trials+=1
    return trials
def locks():
    targets=["method_lock.json","chain_method_lock.json","opt_method_lock.json","decision_lock.json","chain_lock.json","opt_lock.json"];ct=0
    for name in targets:
        o=get(D/name);o=o.get("source",o)
        for n,ch in o.items():
            p=D/Path(n)
            assert h(p)==ch,(name,n);ct+=1
    return ct
def main():
    nlocks=locks();dp=brute();res={};projects=[];cases=[];spot_count=0
    old=replay.old;ew=get(replay.R2/"edit_memory/model.json")["flat"];wm=get(replay.R2/"span_memory/width_model.json");off=get(replay.R2/"span_memory/offset.json")["intercept"]
    for panel,prefix,scorefile in [("first","sealed","per_cut"),("external","opt","opt_scored")]:
        src=D.parent/"context";src=src if panel=="first" else src/"replication"
        scored={(r[0],r[1]):r for r in read(D/(scorefile+".jsonl.gz"))}
        hybridscore={(r[0],r[1]):r for r in read(D/"hybrid_scores.jsonl.gz")} if panel=="first" else {}
        published=get(D/("results.json" if panel=="first" else "optimal_results.json"));chainpub=get(D/"chain_results.json")
        ids_seen=set();cnt=Counter();hits=Counter();fraction=Counter();starts=Counter();h_hits=Counter();tokens=Counter()
        for k in range(8):
            current={r["instance"]:r for r in read(src/f"source_{k}.jsonl.gz")}
            chosen=min(current,key=lambda i:hashlib.sha256(("auditR3F|"+i).encode()).hexdigest())
            chain={r[0]:r[1:] for r in read(D/f"hybrid_{k}.jsonl.gz")} if panel=="first" else {}
            for iid,catalog,cuts,usage in read(D/f"{prefix}_{k}.jsonl.gz"):
                assert iid not in ids_seen;ids_seen.add(iid);source=current[iid];events=source['events'];assert [a[0] for a in cuts]==list(range(4,len(events),4))
                catcost=[len((render(r)+"\n").encode("utf8")) for r in catalog]
                for a,u in usage.items():
                    cap=int(a.split('@')[-1])
                    if cap:assert u.get('retained_bytes_max',0)<=cap
                if chain:
                    hcat,hcuts=chain[iid];assert [t for t,r in hcuts]==[t for t,r in cuts]
                if iid==chosen:
                    arms=("lru","point","typed","chain_exact") if panel=="external" else ("lru","point","typed","placebo")
                    stores={(a,b):(optimal.Extended() if panel=="external" else replay.Memory()) for a in arms for b in replay.BUDGETS}
                    # A hidden future is unavailable, even through obj. Access to any other key immediately fails.
                    visible={"issue":source["issue"],"instance":iid}
                state={"rebase":{}};meta=replay.newmeta();cut_by_t=dict(cuts)
                for t,event in enumerate(events,1):
                    # Build an independent unbounded projection from event prefixes using the canonical source parser.
                    if event[0] in ("str_replace_editor","str_replace_based_edit_tool","edit_file"):
                        replay.advance(state,meta,event,t)
                    if iid==chosen:
                        for (a,b),m in stores.items():
                            m.step(event,t,a,b,visible,ew,wm,off)
                            budget_now=sum(len((render([p,lo,hi,body])+"\n").encode()) for p,lo,hi,age,body in replay.pages(m.state["rebase"]))
                            assert budget_now<=b;cnt["incremental_sample_budgets"]+=1
                    if t not in cut_by_t:continue
                    snap=cut_by_t[t];cnt["boundaries"]+=1
                    unbounded=[(p,lo,hi,txt) for p,lo,hi,age,txt in replay.pages(state["rebase"])]
                    assert sorted(unbounded)==sorted(tuple(catalog[j]) for j in snap["unbounded@0"])
                    if iid==chosen:
                        for (a,b),m in stores.items():
                            curr=sorted((p,lo,hi,txt) for p,lo,hi,age,txt in replay.pages(m.state["rebase"]))
                            assert curr==sorted(tuple(catalog[j]) for j in snap[f"{a}@{b}"]);spot_count+=1
                    q=goal(events,t)
                    gold=oracle(catalog,snap["unbounded@0"],q) if q else []
                    if q:cnt["accepted"]+=1;cnt["reachable"]+=int(bool(gold))
                    for arm,ix in snap.items():
                        cap=int(arm.split('@')[-1]);assert len(ix)==len(set(ix))
                        size=sum(catcost[j] for j in ix)
                        if cap:assert size<=cap;cnt["bounded_payloads"]+=1
                        if q:
                            take=matches(catalog,ix,q[0],gold);assert take==scored[(iid,t)][3][arm]
                            hits[arm]+=take[0];fraction[arm]+=take[1];starts[arm]+=take[2]
                    if chain:
                        ht,hplans=hcuts[t//4-1];assert ht==t
                        for name,(ix,wire) in hplans.items():
                            writer,reader,b=name.split("/");blocks=[render(hcat[j]) for j in ix]
                            assert price("\n".join(blocks))==wire<=512
                            assert sum(price(s) for s in blocks)+max(0,len(blocks)-1)<=512
                            resident=dict(kv for j in snap[writer+"@"+b] for kv in index(catalog[j]))
                            assert all(resident.get(coord)==val for j in ix for coord,val in index(hcat[j]))
                            cnt["validated_read_packets"]+=1
                            if q:
                                take=matches(hcat,ix,q[0],gold);assert [take[0],take[1],wire]==hybridscore[iid,t][2][name];h_hits[name]+=take[0];tokens[name]+=wire
        assert len(scored)==cnt["accepted"] and published["n"]==cnt["accepted"] and len(ids_seen)==published["instances"]
        for a,v in published["arms"].items():
            assert hits[a]==v['hits' if panel=="first" else 'whole'] and starts[a]==v['start_hits' if panel=="first" else 'start']
            assert abs(v['line_fraction' if panel=="first" else 'fraction']-fraction[a]/cnt["accepted"])<1e-10
        if panel=="first":
            assert len(hybridscore)==cnt["accepted"]
            for a,v in chainpub["arms"].items():assert h_hits[a]==v["whole"] and abs(tokens[a]/cnt["accepted"]-v["mean_tokens"])<1e-8
        projects.append({i.split(".")[0] for i in ids_seen});cases.append(ids_seen);res[panel]=dict(counts=cnt,projects=len(projects[-1]),instances=len(ids_seen),resident_hits=hits,hybrid_hits=h_hits)
    assert not projects[0]&projects[1] and not cases[0]&cases[1]
    res.update(status="passed",lock_members=nlocks,independent_exact_dp_cases=dp,masked_future_spot_snapshots=spot_count,shared_projects=0,shared_instances=0)
    res["measurement_limits"]=["Only serialized resident page payload bytes count in the original writer cap. Python metadata, models, process memory and catalogs outside the policy are separate.","The actual input loop supplies prior recorded actor actions. This is offline replay measuring source availability, not renewed solved issues or live agent pass@1.","Determinism spot checks fed only issue and instance fields to policies, never future events."]
    (D/"audit_independent.json").write_text(json.dumps(res,indent=1),encoding="utf8")
    print({k:v['counts'] for k,v in res.items() if isinstance(v,dict) and 'counts' in v})
if __name__=="__main__":main()

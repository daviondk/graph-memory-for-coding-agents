"""After-the-fact constrained oracle for disjoint source blocks, independently of model rankings."""
from collections import Counter,defaultdict
import gzip
import json
import sys
from tail import D,E5,FT,OW,OFF,load,put,pilot
def merged(ranges):
    result=[]
    for a,b in sorted(ranges):
        if result and a<=result[-1][1]:result[-1]=(result[-1][0],max(b,result[-1][1]))
        else:result.append((a,b))
    return result
def residual(need,got):
    result=[]
    for a,b in merged(need):
        cur=a
        for p,q in merged(got):
            if q<=cur:continue
            if p>=b:break
            if cur<p:result.append((cur,min(p,b)))
            cur=max(cur,q)
            if cur>=b:break
        if cur<b:result.append((cur,b))
    return result
def diagnose(model):
    src=E5 if model=="frozen" else FT;seal=load(model+"-source.json");truth=load(OFF/"gold-spans.json.gz")
    outcomes=load(model+"-outcomes.json.gz");cohort={};reasons=Counter();loss=Counter();win=Counter()
    for i in range(8):
        fname=f"forecasts-main-{i}.json.gz";assert pilot.sha(src/fname)==seal["ranks"][fname]
        rawrank={q["q"]:q for q in load(src/fname)};bn=f"forecast-{i}.jsonl.gz";assert pilot.sha(OW/bn)==seal["blocks"][bn]
        picked=load(f"{model}-picks-{i}.json.gz")
        with gzip.open(OW/bn,"rb") as records:
            for rec,line in zip(picked,records,strict=True):
                block=json.loads(line);assert rec["t"]==block["t"]
                table={tuple(x):j for j,x in enumerate(block["addresses"])}
                bins=defaultdict(list);refs=defaultdict(list)
                first=rawrank[next(iter(rec["q"]))]
                for n in first["rr"]:
                    s=n["source_spans"][0];e=table[s["event_id"],s["json_pointer"]];refs[e].append((s["char_start"],s["char_end"]))
                for j,(e,a,b,c,nb) in enumerate(block["blocks"]):
                    allowed=any(p<=a and b<=q for p,q in refs[e])
                    bins[e].append((a,b,c,allowed))
                for qid,p in rec["q"].items():
                    need=defaultdict(list);got=defaultdict(list)
                    for e in truth[qid]:need[table.get((e["event_id"],e["json_pointer"]),-1)].append((e["char_start"],e["char_end"]))
                    for k in p["core"]:
                        e,a,b,c=rec["nodes"][k];got[e].append((a,b))
                    needed=0;covered=0;excluded=0;source_gap=0;cost=0
                    for e,segments in need.items():
                        miss=residual(segments,got[e]);needed+=sum(y-x for x,y in miss)
                        for a,b,c,ok in bins[e]:
                            hits=sum(max(0,min(b,y)-max(a,x)) for x,y in miss)
                            covered+=hits
                            if hits:
                                if not ok:source_gap+=hits
                                elif any(p0<b and a<p1 for p0,p1 in got[e]):excluded+=hits
                                else:cost+=c
                    assert covered<=needed
                    if not needed:reason="already_core"
                    elif covered<needed or source_gap:reason="missing_from_source_or_parent"
                    elif excluded:reason="intersects_core"
                    elif cost>p["remaining"]:reason="cost"
                    else:reason="reachable"
                    feasible=reason in ("already_core","reachable")
                    for a in ("a","b","c"):assert feasible>=bool(outcomes[qid][a]["full_support"])
                    assert (reason=="already_core")==bool(outcomes[qid]["core"]["full_support"])
                    record={"t":rec["t"],"reason":reason,"feasible":feasible,"residual_chars":needed,"uncovered_source_chars":needed-covered+source_gap,
                            "blocked_overlap_chars":excluded,"token_cost_of_required_eligible_fine":cost,"remaining":p["remaining"]}
                    cohort[qid]=record;reasons[reason]+=1
                    if outcomes[qid]["related"]["full_support"]>outcomes[qid]["b"]["full_support"]:loss[reason]+=1
                    if outcomes[qid]["b"]["full_support"]>outcomes[qid]["related"]["full_support"]:win[reason]+=1
    assert len(cohort)==2000
    result={"all":dict(reasons),"b_losses_against_related":dict(loss),"b_wins_against_related":dict(win),"fine_oracle_full":sum(r["feasible"] for r in cohort.values())}
    put(model+"-oracle-rows.json.gz",cohort);put(model+"-oracle.json",result);print(model,result,flush=True)
if __name__=="__main__":diagnose(sys.argv[1])

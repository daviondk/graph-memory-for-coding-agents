"""Determine eligibility at write time and observe subsequent explicit editor events."""
from native import D,P,V,S,sha,h,get,save
from collections import Counter,defaultdict
from bisect import bisect_right

def cap(path, pairs,limit=128):
    return sorted(sorted(pairs,key=lambda z:(h("R37-128|"+path+"|"+str(z[0])),z[0]))[:limit])

CLOSED={"mutation","finished"}
def windows(events,offset,path,native,starts,allow_opaque):
    r=0;anyview=0;numbered=0;first=None;crossed=0
    stop="trace_end_error" if native["run_error"] else "trace_end_unverified"
    at=native["last"]
    for j in range(offset+1,len(events)):
        e=events[j];k=e[1]
        if k in ("barrier","gap"):
            crossed+=1
            if allow_opaque and k=="barrier":continue
            stop="opaque" if k=="barrier" else "gap";at=e[0];break
        if k=="finish":stop="finished";at=e[0];break
        if len(e)<3 or e[2]!=path:continue
        if k=="read":
            anyview+=1;numbered+=e[4]>0
            if e[3]:
                r+=1
                if first is None:first=e[0]
        elif k=="write_start":
            ack=starts.get(e[0])
            if ack is None:
                stop="unconfirmed_write";at=e[0];break
            close,cmd,ph=ack;assert ph==h(path) and close>e[0]
            overlap=any((x[1] in ("barrier","gap") or (len(x)>2 and x[2]==path and x[1] in ("write_start","read","edit","other")))
                        for x in events[j+1:] if x[0]<close)
            if overlap:
                stop="inflight_write";at=e[0];break
            stop="mutation";at=close;break
        elif k in ("edit","other"):
            stop="mutation";at=e[0];break
    return dict(reads=r,any_view=anyview,numbered_view=numbered,first=first,stop=stop,end=at,opaque_events=crossed)

def build():
    bound=get(D/"native_boundaries.json.gz");bseal=get(D/"boundary-seal.json");assert bseal["data"]==sha(D/"native_boundaries.json.gz")
    corpus=get(V/"events.json.gz");assert set(corpus)==set(bound)
    original={(p["rid"],p["edit"]):p for p in get(V/"predictions.json.gz")}
    assert len(original)==1282
    store=get(S/"prefix_inputs.json.gz");out=[];inputs={};flow=defaultdict(Counter)
    for rid,v in corpus.items():
        na=bound[rid];cat="main" if v["subset"] in ("predecessors","main_takeovers") else "secondary"
        z=flow[cat];z["runs"]+=1
        if na.get("empty"):
            assert not v["events"];continue
        events=list(v["events"])+[[a+.5,"gap"] for a,b in na["gaps"]]
        if na["finished"] is not None:events.append([na["finished"],"finish"])
        events.sort(key=lambda e:e[0]);assert len({e[0] for e in events})==len(events)
        starts={a:(b,cmd,ph) for a,b,cmd,ph in na["successful_writes"]}
        last_opaque=-1;history={}
        for j,e in enumerate(events):
            k=e[1];i=e[0]
            if k in ("barrier","gap"):
                last_opaque=i;continue
            if k=="finish":continue
            path=e[2]
            if k=="read":history[path]=(i,e[3],[]);continue
            if k=="write_start":
                if path in history:history[path][2].append(i)
                continue
            if k not in ("edit","other"):continue
            prev=history.pop(path,None)
            if k!="edit":continue
            z["all_successful_replaces"]+=1
            edit=e[3]
            if not edit["matched"]:continue
            z["matched_replaces"]+=1
            if prev is None or not prev[1]:
                z["no_uncleared_prior_informative_view"]+=1;continue
            z["with_uncleared_prior_informative_view"]+=1
            if prev[2]!=[edit["action_index"]] or not prev[0]<edit["action_index"]<i:
                z["competing_attempt"]+=1;continue
            assert starts[edit["action_index"]]==(i,"str_replace",h(path))
            clean=last_opaque<prev[0]
            z["enrolled_clean" if clean else "enrolled_opaque_prefix"]+=1
            q=h("demand|"+rid+"|"+str(i));assert q not in inputs
            strict=windows(events,j,path,na,starts,False);loose=windows(events,j,path,na,starts,True)
            assert strict["reads"]<=loose["reads"]
            prevstudy=original.get((rid,i))
            if prevstudy:
                assert prevstudy["prev"]==prev[0] and prevstudy["next"]==loose["first"]
            row=dict(q=q,rid=rid,issue=v["issue"],repo=v["repo"],cohort=cat,prefix="clean" if clean else "opaque",
                prev=prev[0],edit=i,strict=strict,ignore_opaque=loose,old=prevstudy["q"] if prevstudy else None)
            # Inputs below have no future read count or stop type: schedule is kept in a separate file.
            inp=dict(path=path,base=cap(path,prev[1]),receipt=cap(path,edit["rows"]),start=edit["k"],delta=edit["delta"],
                     end=(None if edit["k"] is None else edit["k"]+edit["old_breaks"]))
            if prevstudy:
                p=store[prevstudy["q"]]
                for field in inp:assert inp[field]==p[field],field
            inputs[q]=inp;out.append(row)
    # Former study selected 1282 same-path revisits; active write histories can be checked directly.
    assert sum(r["old"] is not None for r in out)==1282
    save(D/"demand-seal.json",dict(program=sha(D/"count.py"),protocol=sha(D/"PROTOCOL_RU.md"),native=sha(D/"native_boundaries.json.gz"),
       future=save(D/"followup.json.gz",out),prefixes=save(D/"prefixes.json.gz",inputs),flow=flow))
    print({k:dict(v) for k,v in flow.items()})
    print(Counter((r["cohort"],r["prefix"],r["strict"]["stop"],bool(r["strict"]["reads"])) for r in out))
if __name__=="__main__":build()

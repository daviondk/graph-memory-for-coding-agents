"""Score actual next-view addresses, including false-positive and unobservable errors."""
from collections import Counter,defaultdict
from predict import D,STORE,VIS,ARMS,load,put,sha
import numpy as np

def ratio(a,b):
    return a/b if b else None

def annotate(q,stored,gold):
    g=dict(gold);r=dict(stored["receipt"]);old={n:(h,side) for n,h,side in stored["old"]}
    w=stored["witness"]
    bad={s:any(not flag for _,flag in obs) for s,obs in w.items()}
    conflict=any(bad.values())
    candidates=dict(r)
    candidates.update({n:h for n,(h,_) in old.items()})
    assert len(candidates)==len(r)+len(old)
    stat=Counter(episodes=1,visible=len(g),hypotheses=len(candidates),carried_slots=len(old),receipt_slots=len(r))
    stat.update(dict(overlaps=sum(len(obs) for obs in w.values()),mismatches=sum(not flag for obs in w.values() for _,flag in obs),
                     any_overlap=int(any(w.values())),any_conflict=int(conflict),has_carried=int(bool(old)),
                     left_conflict=int(bad["left"]),right_conflict=int(bad["right"])))
    obsright={n for n,h in candidates.items() if n in g and g[n]==h}
    obswrong={n for n,h in candidates.items() if n in g and g[n]!=h}
    oldright=set(old)&obsright; oldwrong=set(old)&obswrong
    stat.update(dict(correct=len(obsright),wrong=len(obswrong),correct_carried=len(oldright),wrong_carried=len(oldwrong),
                     correct_receipt=len(obsright-set(old)),wrong_receipt=len(obswrong-set(old)),
                     any_wrong=int(bool(obswrong)),alert_and_wrong=int(conflict and bool(obswrong)),
                     alerted_carried_wrong=int(conflict)*len(oldwrong),
                     alerted_any_wrong=int(conflict)*len(obswrong),
                     alerted_carried_correct=int(conflict)*len(oldright),
                     same_side_wrong=sum(bad[old[n][1]] for n in oldwrong),
                     same_side_correct=sum(bad[old[n][1]] for n in oldright)))
    for method,addresses in stored["drop"].items():
        rm=set(addresses)
        assert rm<=set(old)
        stat[method+"_removed"]=len(rm)
        stat[method+"_lost_correct"]=len(rm&obsright)
        stat[method+"_removed_wrong"]=len(rm&obswrong)
        if method in ("side","local"):
            proportion=len(rm)/len(old) if old else 0.
            stat[method+"_random_expected_lost_correct"]=proportion*len(oldright)
            stat[method+"_random_expected_removed_wrong"]=proportion*len(oldwrong)
    return dict(issue=stored["issue"],zone=stored["zone"],stats=dict(stat))

def group(rows):
    counts=Counter();issues=defaultdict(Counter)
    for r in rows:
        counts.update(r["stats"]);issues[r["issue"]].update(r["stats"])
    assert len(rows)==counts["episodes"]
    keys=sorted(issues);rng=np.random.default_rng(38199)
    draws=rng.integers(len(keys),size=(10000,len(keys)))
    def interval(data):
        return dict(value=float(data.mean()),ci95=np.quantile(data[draws].mean(1),[.025,.975]).tolist())
    arms={}
    for a in ARMS:
        delta=np.array([[-issues[i][a+"_lost_correct"]/issues[i]["visible"],-issues[i][a+"_removed_wrong"]/issues[i]["visible"]] for i in keys])
        arms[a]=dict(delta_coverage=interval(delta[:,0]),delta_error=interval(delta[:,1]))
    return dict(counts=dict(counts),issues=len(issues),correct_coverage_macro=np.mean([issues[i]["correct"]/issues[i]["visible"] for i in keys]),
            error_rate_macro=np.mean([issues[i]["wrong"]/issues[i]["visible"] for i in keys]),arms=arms,
            upper_any=ratio(counts["alerted_carried_wrong"],counts["wrong"]),
            upper_side=ratio(counts["same_side_wrong"],counts["wrong"]),
            conflict_episodes=[r["q"] for r in rows if r["stats"]["any_conflict"]])
def main():
    seal=load(D/"seal.json")
    assert sha((D/"predictions.json.gz").read_bytes())==seal["result"]
    assert sha((STORE/"reference.json.gz").read_bytes())==load(STORE/"manifest.json")["files"]["reference.json.gz"]
    results=load(D/"predictions.json.gz");refs=load(STORE/"reference.json.gz")
    observations=load(VIS/"observations.json.gz");past=load(VIS/"predictions.json.gz")
    events={key:[e[0] for e in row["events"] if e[1]=="barrier"] for key,row in load(VIS/"events.json.gz").items()}
    assert set(results)==set(refs)==set(observations)
    out=[]
    for p in past:
        q=p["q"];r=results[q]
        joined=dict(r["receipt"])|{n:h for n,h,s in r["old"]}
        assert sorted(joined.items())==sorted(dict(refs[q]).items())
        row=annotate(q,r,observations[q]["observed"])
        row["q"]=q
        before=any(p["prev"]<j<p["edit"] for j in events[p["rid"]])
        after=any(p["edit"]<j<p["next"] for j in events[p["rid"]])
        assert (before or after)==(p["window"]=="opaque")
        row["barrier_before"]=before;row["barrier_after"]=after;out.append(row)
    groups={name:group([r for r in out if r["zone"]==name]) for name in sorted({r["zone"] for r in out})}
    previous=load(VIS/"results.json")["groups"]
    for name,g in groups.items():
        ref=previous[name]["methods"]["T"]
        assert g["counts"]["correct"]==ref["correct"] and g["counts"]["wrong"]==ref["wrong"] and abs(g["correct_coverage_macro"]-ref["coverage"])<1e-12
    timing={}
    for row in out:
        key="before="+str(int(row["barrier_before"]))+",after="+str(int(row["barrier_after"]))
        tally=timing.setdefault(key,Counter());tally.update(row["stats"])
    put("scored.json.gz",out)
    put("results.json",dict(groups=groups,total=group(out),barrier_timing=timing,
                            predictions=seal["result"],score=sha((D/"scored.json.gz").read_bytes())))
    for name,g in groups.items():
        c=g["counts"];print(name,[(k,c[k]) for k in ("episodes","any_overlap","any_conflict","mismatches","wrong","wrong_receipt","alerted_carried_wrong","same_side_wrong","side_lost_correct","local_lost_correct","local_removed_wrong")])
if __name__=="__main__":main()


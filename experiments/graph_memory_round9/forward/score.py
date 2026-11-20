"""Score fixed binary roles, concrete target addresses, and joint outputs with cluster bootstrap."""
from collections import Counter,defaultdict
import random
from common import *

ARMS=("disappear","git_prior","lex_prior","edge","edge_lex_agree")
def get_target(candidates, label):
    owner,name,types=label
    ms=[a for a in candidates if a[1]==owner and a[2]==name and len(a[3])==len(types)]
    if len(ms)>1:ms=[a for a in ms if a[3]==types]
    return ms
def summarize(rs):
    counts={}
    for arm in ARMS:
        tp=sum(x["inline"] and x["predicted"][arm] for x in rs)
        fp=sum(not x["inline"] and x["predicted"][arm] for x in rs)
        fn=sum(x["inline"] and not x["predicted"][arm] for x in rs)
        tn=len(rs)-tp-fp-fn
        counts[arm]=dict(tp=tp,fp=fp,fn=fn,tn=tn,balanced=(tp/(tp+fn)+tn/(tn+fp))/2 if tp+fn and tn+fp else None,
                         address=sum(r["address_hit"][arm] for r in rs),joint=sum(r["joint_hit"][arm] for r in rs))
    return dict(n=len(rs),commits=len({x['commit'] for x in rs}),
                resolved=sum(x["gold_count"]==1 for x in rs),arms=counts)
def contrasts(rs,base,arm):
    groups=defaultdict(lambda:[0,0,0,0,0,0,0])
    for r in rs:
        v=groups[r["commit"]];v[6]+=1
        idx=0 if r["inline"] else 1
        v[idx]+=1
        v[idx+2]+=int(r["predicted"][arm]==r["inline"])-int(r["predicted"][base]==r["inline"])
        v[4]+=r["address_hit"][arm]-r["address_hit"][base]
        v[5]+=r["joint_hit"][arm]-r["joint_hit"][base]
    def effect(v):
        pos,neg,dp,dn,da,dj,n=v
        return [50*(dp/pos+dn/neg),100*da/n,100*dj/n] if pos and neg else None
    vals=list(groups.values())
    rng=random.Random(19021)
    boot=[[] for _ in range(3)]
    for _ in range(10000):
        one=effect(list(map(sum,zip(*rng.choices(vals,k=len(vals))))))
        if one:
            for k,b in enumerate(boot):b.append(one[k])
    obs=effect(list(map(sum,zip(*vals))))
    paired={}
    for i,k in enumerate(["balanced","address","joint"]):
        d=sorted(boot[i]);paired[k]=dict(delta_pp=obs[i],ci95=[d[int(.025*(len(d)-1))],d[int(.975*(len(d)-1))]])
    return paired
def main():
    check(read("prediction-lock.json"));check(read("selection.json")["files"])
    labels=read("labels.json");out=[]
    for r in read("predictions.json.gz"):
        g=labels[r["case"]];valid=get_target(r["candidates"],g["target"])
        gold=valid[0] if len(valid)==1 else None
        inline=g["role"]=="Inline Method"
        ah={k:bool(gold and r["addresses"][k]==gold) for k in ARMS}
        joint={k:(ah[k] and r["roles"][k]==inline) for k in ARMS}
        out.append(dict(case=r["case"],commit=r["commit"],project=r["project"],kind=g["role"],inline=inline,
                        predicted=r["roles"],gold=gold,gold_count=len(valid),address_hit=ah,joint_hit=joint,
                        n_lost=len(r["lost_callers"]),raw_old_calls=r["old_calls_seen"],candidates=r["candidate_counts"]))
    save("outcomes.json",out)
    summary=summarize(out)
    summary.update(pairs={f"{a} minus {b}":contrasts(out,b,a) for a,b in [
        ("edge","lex_prior"),("edge","git_prior"),("edge","disappear"),("edge","edge_lex_agree"),("lex_prior","git_prior")]})
    summary["project"]={p:summarize([r for r in out if r["project"]==p]) for p in sorted({r["project"] for r in out})}
    summary["kind"]={t:summarize([r for r in out if r["kind"]==t]) for t in sorted({r["kind"] for r in out})}
    save("results.json",summary)
    save("score-lock.json",hashfiles(["score.py","selection.json","prediction-lock.json","labels.json","outcomes.json","results.json"]))
    print(summary["n"],summary["commits"],summary["resolved"])
    print(json.dumps(summary["arms"]))
    print(json.dumps(summary["pairs"]["edge minus lex_prior"]))
if __name__=="__main__":main()

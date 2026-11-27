"""Offline bounds when a checkpoint may use any number of bytes up to its limit."""
from argparse import ArgumentParser
from collections import Counter

from decompose import HERE, bracket, chosen, components, gain, load, panels, prepare, save, source


def evaluate(rows, schedule, observed):
    ops,_=prepare(rows,schedule)
    events,costs,values,bonuses=components(ops)
    net={j:v-2*costs[j] for j,v in values.items()}
    controls=[]
    for name in ("recent","largest","demand"):
        group,used,_=chosen(events,1024,name)
        controls.append(group)
        assert 2*used + 20 == observed[name+"1024"]["paid"]
        achieved=sum(gain(group,net,bonuses))-100
        assert achieved==observed["cold"]["charged"]-observed[name+"1024"]["charged"]
    lower,upper,witness=bracket(costs,net,bonuses,984,controls)
    lower=max(0,lower-100)
    upper=max(0,upper-100)
    if not lower:
        witness=[]
    return dict(lower=lower,upper=upper,witness=witness,
                demand=observed["cold"]["charged"]-observed["demand1024"]["charged"],
                cold=observed["cold"]["charged"],cost_upper=observed["cold"]["charged"]-lower,
                cost_lower=observed["cold"]["charged"]-upper)


def run():
    data=load(HERE.parent/"restart_transfer/no-padding.json")["projects"]
    old=panels()
    projects={}
    summary={}
    for key,rows in data.items():
        name,p=key.split("-")
        histories=old[p] if name=="original" else source(name)[0]
        sums=Counter()
        for repo,observed in rows.items():
            v=evaluate(histories[repo],p,observed)
            sums.update({k:v[k] for k in ("lower","upper","demand","cold","cost_upper","cost_lower")})
            sums.update(projects=1,zero=v["upper"]==0,positive=v["lower"]>0,closed=v["upper"]==v["lower"])
            projects[key+"/"+repo]=v
        summary[key]=sums
    return dict(projects=projects,summary=summary)


if __name__=="__main__":
    ap=ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    out=run()
    file=HERE/"natural-results.json"
    if args.verify:assert out==load(file)
    else:save(file,out)
    print({g:(v["lower"],v["upper"],v["demand"],v["positive"],v["closed"]) for g,v in out["summary"].items()})

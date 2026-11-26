"""Independent decision and timing checks, plus restart tests of the packed BLOB boundary."""
from inputs import D,H,get,sha,put,h
from math import log1p,isclose
from pathlib import Path
from tempfile import TemporaryDirectory
from statistics import mean
from engine import dbopen,compile_model
import packed

def validate_fixtures():
    cases=[]
    # Both constant selections are used to exercise untouched, moved or overwritten first source rows.
    examples=[([],[],None,None,0),([(1,"a")],[],4,4,1),([(3,"b"),(5,"c")],[(3,"Q")],1,1,2),
              ([(3,"p"),(4,"v")],[(3,"first")],3,3,0),([(2,"a"),(10,"b")],[],None,None,0)]
    with TemporaryDirectory(dir=D,prefix="verify_") as td:
        for j,(base,rec,k,z,delta) in enumerate(examples):
            for target in "AL":
                path=Path(td)/(str(j)+target+".db");db=dbopen(path,"H");b=1 if target=="L" else -1
                xs=[(n,h(s)) for n,s in base];rs=[(n,h(s)) for n,s in rec]
                packed.ingest(db,"H",7,xs,"vev",300);db.close();db=dbopen(path,"H",False)
                item=dict(receipt=rs,start=k,end=z,delta=delta,current=650,path="fixture")
                model=compile_model(dict(intercept=b,coef=[0.0]*10));got=packed.edit(db,"H",model,7,None,item)[0];assert got==target
                db.close();db=dbopen(path,"H",False)
                vals,_,_=packed.answer(db,"H",7,"fixture",None);db.close()
                want=dict(rs)
                for n,s in xs:
                    if k is not None and (n<k or n>z):
                        dest=n if n<k else n+delta;want.setdefault(dest,s)
                assert [(n,s.hex()) for n,s in vals]==sorted(want.items())
                cases.append([j,target,len(want)])
    return cases

def run():
    plan=get(D/"plan.json");qids=plan["panel"];inp=get(D/"prefixes.json.gz");fut=get(D/"schedule.json.gz")
    dec=get(H/"decisions.json.gz");mods=get(H/"models.json");first=get(D/"run-seal.json");second=get(D/"packed-run-seal.json")
    assert sha(H/"manifest.json")==plan["parent"] and sha(D/"engine.py")==plan["engine"] and sha(D/"run.py")==plan["timing"]
    assert first["raw"]==sha(D/"raw.json.gz") and second["raw"]==sha(D/"packed-raw.json.gz")
    assert sha(D/"coefficients.bin")==get(D/"packed-plan.json")["coefficients"]["sha"]
    assert sha(D/"packed.py")==get(D/"packed-plan.json")["engine"] and sha(D/"run_packed.py")==get(D/"packed-plan.json")["program"]
    for q in qids:
        x=inp[q];old={n for n,_ in x["base"]};new={n for n,_ in x["receipt"]};k=x["start"];z=x["end"];d=x["delta"]
        vals=[log1p(len(old)),log1p(len(new)),log1p(len(old&new)),log1p(sum(k is not None and n>z and bool(d) for n in old)),
              log1p(sum(k is not None and k<=n<=z for n in old)),log1p(abs(d or 0)),int(k is not None),
              log1p(x["current"]-x["prev"]),log1p(x["past_types"].count("v")),log1p(x["past_types"].count("e"))]
        m=mods[x["repo"]]["ridge"];score=m["intercept"]+sum(w*v for w,v in zip(m["coef"],vals))
        assert dec[q]["H"]==("L" if score>0 else "A")
    result=get(D/"results.json")
    for stage,file in (("initial","raw.json.gz"),("packed","packed-raw.json.gz")):
        series=get(D/file)
        for scen,part in series.items():
            assert set(part)==set(qids)
            for m in "ALH":
                cluster=[]
                for q in qids:
                    reps=part[q];assert len(reps)==6
                    for v in reps:
                        t=v[m];assert t[6]==len(inp[q]["base"])+int(m=="H" and stage=="initial") and t[-1]==fut[q]["reads"]
                        assert t[10]==(int(fut[q]["reads"]>0) if scen=="miss" else 0)
                        assert t[8]==int(scen=="miss" and m!="L")
                    cluster.append(mean(sum(v[m][:3]) for v in reps))
                assert isclose(mean(cluster),result[stage][scen]["costs"]["ns"]["lifecycle"]["mean"][m])
    cases=validate_fixtures();put(D/"independent.json",dict(episodes=len(qids),schedules=2,versions=2,fixture_restarts=cases,labels_match=True))
    print("Verified 128 frozen labels, both runtime stages and cache schedules; 10 additional BLOB/restart cases.")
if __name__=="__main__":run()

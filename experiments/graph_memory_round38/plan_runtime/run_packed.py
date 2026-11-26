"""Repeat the same paired schedules with the independently sealed in-row representation."""
from inputs import *
from run import cycles,reference
from engine import dbopen,compile_model
from packed import build_tables,load_tables,ingest,edit,answer
from tempfile import TemporaryDirectory
from itertools import permutations
from time import perf_counter_ns

def run():
    p=get(D/"plan.json");previous=get(D/"primary-seal.json")
    assert previous["raw"]==sha(D/"raw.json.gz") and previous["secondary_protocol"]==sha(D/"PACKED_ADDENDUM_RU.md")
    panel=p["panel"];src=get(D/"prefixes.json.gz");sc=get(D/"schedule.json.gz");dec=get(H/"decisions.json.gz");mods=get(H/"models.json")
    coef=build_tables();expected={q:reference(src[q]) for q in panel}
    put(D/"packed-plan.json",dict(prior=sha(D/"primary-seal.json"),program=sha(Path(__file__)),engine=sha(D/"packed.py"),coefficients=coef))
    for q in panel:assert [n for n,_ in src[q]["base"]]==sorted(n for n,_ in src[q]["base"])
    for r,m in load_tables(mods).items():assert m==compile_model(mods[r]["ridge"])
    samples={s:{q:[] for q in panel} for s in ("resident","miss")};startup={s:[] for s in samples}
    orders=list(permutations("ALH"))
    with TemporaryDirectory(dir=D,prefix="packed_") as td:
        temp=Path(td)
        for rep in range(-1,6):
            for scen in (("resident","miss") if rep%2==0 else ("miss","resident")):
                w=perf_counter_ns();c=cycles();frozen=load_tables(mods);cpu=cycles()-c;wall=perf_counter_ns()-w
                if rep>=0:startup[scen].append([wall,cpu])
                db={m:dbopen(temp/(scen+m+str(rep)+".db"),m) for m in "ALH"}
                for i,q in enumerate(panel):
                    x=src[q];trial={}
                    for m in orders[(max(rep,0)+int(h("R38-plan-order|"+q)[:16],16))%6]:
                        con=db[m];model=frozen[x["repo"]];before=con.total_changes
                        w=perf_counter_ns();c=cycles()
                        old=ingest(con,m,i,x["base"],x["past_types"],x["prev"])
                        ci=cycles()-c;wi=perf_counter_ns()-w;nr=con.total_changes-before
                        if scen=="miss":old=None
                        before=con.total_changes;w=perf_counter_ns();c=cycles()
                        selected,st,ps,pr=edit(con,m,model,i,old,x)
                        ce=cycles()-c;we=perf_counter_ns()-w;nw=con.total_changes-before
                        assert m!="H" or selected==dec[q]["H"]
                        if scen=="miss":st=None
                        R=sc[q]["reads"];trips=num=0
                        if R:
                            w=perf_counter_ns();c=cycles();outs=[]
                            for _ in range(R):
                                out,t,n=answer(con,m,i,x["path"],st);trips+=t;num+=n;st=("ready",out);outs.append(out)
                            cr=cycles()-c;wr=perf_counter_ns()-w
                            assert all(v==expected[q] for v in outs)
                        else:cr=wr=0
                        trial[m]=[wi,we,wr,ci,ce,cr,nr,nw,ps,pr,trips,num,R]
                    if rep>=0:samples[scen][q].append(trial)
                for con in db.values():con.close()
        # Check both true connection boundaries independently for every held-out episode, including zeros.
        dbpath=temp/"resumed.db";con=dbopen(dbpath,"H")
        for i,q in enumerate(panel):
            x=src[q];ingest(con,"H",i,x["base"],x["past_types"],x["prev"])
        con.close();con=dbopen(dbpath,"H",False)
        for i,q in enumerate(panel):
            x=src[q];choice,*_=edit(con,"H",frozen[x["repo"]],i,None,x);assert choice==dec[q]["H"]
        con.close();con=dbopen(dbpath,"H",False)
        for i,q in enumerate(panel):assert answer(con,"H",i,src[q]["path"],None)[0]==expected[q]
        con.close()
    put(D/"packed-run-seal.json",dict(plan=sha(D/"packed-plan.json"),raw=put(D/"packed-raw.json.gz",samples),compile_all=startup,verified_actual_restarts=len(panel)))
if __name__=="__main__":run()

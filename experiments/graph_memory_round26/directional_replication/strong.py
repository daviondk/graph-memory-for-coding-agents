from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
import sys
from rep_io import *
from cohort import body,digest
import runpy
_eval=runpy.run_path(str(D/"evaluate.py"),run_name="replication_metrics")
true_spans,annotate,resample=(_eval[name] for name in ("true_spans","annotate","resample"))
sys.path.insert(0,str(R))
from dataset import Tokenizer,TOK
import direction

from statistics import mean
def worker(i):
    c=read(D/"choices-lock.json")["files"][i];r=read(D/"read-lock.json")["files"][i]
    assert sha(D/c[0])==c[1] and sha(D/r[0])==r[1]
    choices=read(D/c[0]);old=read(D/r[0]);by=defaultdict(list)
    for q,z in choices.items():by[z["t"]].append(q)
    direction.PAIRS=(("both","adaptive"),);tok=Tokenizer.from_file(str(TOK));out={}
    for a in read(TRAIN)["data"]:
        title=a["title"]
        if title not in by:continue
        src=body(a)
        for q in by[title]:
            new=direction.execute(tok,choices[q]["cut"],src);assert new["arms"]==old[q]["arms"]
            out[q]=new["equal"]["both-adaptive"]
    assert set(out)==set(old)
    p=D/f"strong-{i}.json.gz";return [p.name,save(p,out)]
def main():
    lock=D/"strong-lock.json"
    if not lock.exists():
        with ProcessPoolExecutor(2) as ex:files=list(ex.map(worker,range(8)))
        save(lock,{"files":files,"plan":sha(D/"STRONG_CONTROL_RU.md"),"primary":sha(D/"results.json"),"script":sha(Path(__file__))})
    co=read(D/"cohort.json.gz");ids={q for r in co["panel"].values() for q in r["ids"]};g,quality=true_spans(ids)
    rows=[];mech=defaultdict(int)
    for i,(name,h) in enumerate(read(lock)["files"]):
        assert sha(D/name)==h
        z=read(D/name);chs=read(D/f"choices-{i}.json.gz");ori=read(D/f"read-{i}.json.gz")
        for q,(a,b) in z.items():
            r=chs[q];base=r["base"];goals=g[q]
            if not goals:continue
            va,vb=[annotate(base,v,goals) for v in (a,b)];assert va[2]==vb[2]
            rows.append({"q":q,"t":r["t"],"a":va,"b":vb})
            left_right,right=ori[q]["equal"]["both-right"]
            right_leg=[v for v in left_right if v[5]=="R"];left_leg=[v for v in left_right if v[5]=="L"]
            if right_leg:
                assert len(right_leg)==len(right)==1 and right_leg[0][1]==right[0][1] and right_leg[0][2]<=right[0][2]
            first=annotate(base,left_right,goals)[0];control=annotate(base,right,goals)[0]
            if first>control:
                mech["wins"]+=1
                assert not annotate(base,right_leg,goals)[0]
                mech["left_alone_sufficient"]+=annotate(base,left_leg,goals)[0];mech["requires_both_sides"]+=not annotate(base,left_leg,goals)[0]
            if first<control:
                assert right and right[0][2]>(right_leg[0][2] if right_leg else right[0][1])
                mech["right_truncation_losses"]+=1
    rows.sort(key=lambda z:z["q"]);h=save(D/"strong-outcomes.json.gz",rows)
    data={"strong":{"hits":[sum(r[k][0] for r in rows) for k in ("a","b")],"coverage":[mean(r[k][1] for r in rows) for k in ("a","b")],"mean_tokens":mean(r["a"][2] for r in rows),"primary_cost_formula":True,
        "paired":resample(rows,"t",lambda r:r["a"][0]-r["b"][0],263117)},"mechanism":dict(mech),"rows":h,"seal":sha(lock)}
    save(D/"strong-results.json",data);print(data)
if __name__=="__main__":main()

"""Paired multi-session metadata memory with author-native MemoryStore/RetrievalGate and batched inspections."""
from artifacts import *
from functools import lru_cache
from collections import defaultdict,Counter
from random import Random
import sys
sys.path.insert(0,str(ROOT/"upstream/src"))
from dream_memory.memory_store import MemoryStore
from dream_memory.retrieval import RetrievalGate
from dream_memory.schemas import MemoryItem,MemoryType,Provenance
POLICIES=["none","previous","current_static","same_file","typed","static_else_previous","pkg_info"]
def yes(val,basis):return dict(present=True,value=val,basis=basis)
def no():return dict(present=False,value=None,basis="abstained")
def forecasts():
    projects=get(ROOT/"releases.json");plans=[];native=[];trans=[];sources_cache={}
    for name,r in projects.items():
        for y1,y2 in zip(YEARS,YEARS[1:]):
            old=r["snapshots"].get(str(y1));new=r["snapshots"].get(str(y2))
            if not old or not new or old["version"]==new["version"]:continue
            key=f"{name}/{y2}";reference=wheel(old["wheel"])
            for entry in (old["sdist"],new["sdist"]):
                if entry["sha256"] not in sources_cache:sources_cache[entry["sha256"]]=sources(entry)
            before=sources_cache[old["sdist"]["sha256"]];after=sources_cache[new["sdist"]["sha256"]]
            store=MemoryStore(namespace=key);gate=RetrievalGate(store)
            def identifier(f):return f"{name}:{old['version']}:{f}"
            for f in FACETS:
                content=json.dumps(dict(facet=f,value=reference["fields"][f],wheel=old["version"]),sort_keys=True)
                store.add(MemoryItem(content=content,type=MemoryType.SEMANTIC_PROJECT,
                     provenance=Provenance(file_paths=[reference["member"]],command_outputs=[reference["member_sha"],old["wheel"]["sha256"]]),
                     write_reason="Observed installed distribution metadata from the previous wheel",id=identifier(f),
                     repo_scope=name,symbol_scope=[f],created_at=f"{y1}-06-30T00:00:00Z",updated_at=f"{y1}-06-30T00:00:00Z"))
            trans.append(dict(key=key,name=name,year=y2,old=old["version"],new=new["version"],old_wheel=reference,
                previous_sdist_sha=old["sdist"]["sha256"],current_sdist_sha=new["sdist"]["sha256"],new_wheel_sha=new["wheel"]["sha256"],
                py_bytes=after["py_bytes"],pkg_info_bytes=after["pkg_info_bytes"],wheel_archive_bytes=new["wheel"]["size"]))
            for f in FACETS:
                q=dict(text=f"What is the distribution metadata field {f} for {name} {new['version']}?",repo_scope=name,symbols=[f],time=f"{y2}-06-30T00:00:00Z",token_budget_read=200)
                got=gate.retrieve(q,k=1)
                native.append(dict(key=key,facet=f,query=q,items=[i.to_dict() for i in got],decisions=list(gate.last_decisions)))
                hist=yes(json.loads(got[0].content)["value"],"previous wheel") if len(got)==1 and got[0].id==identifier(f) else no()
                o,n=before["fields"][f],after["fields"][f]
                current=yes(n,"explicit declared source") if n is not None else no()
                full=before["py_sha"] is not None and before["py_sha"]==after["py_sha"]
                if hist["present"] and o is not None and o==n:
                    typed=yes(hist["value"],"same declared field, old observed wheel")
                elif hist["present"] and n is not None and o is not None and o==hist["value"]:
                    typed=yes(n,"changed declared field, agrees on previous wheel")
                else:typed=no()
                opts=[no(),hist,current,hist if full else no(),typed,current if current["present"] else hist,
                      yes(after["pkg_info"][f],"current source distribution PKG-INFO") if after["pkg_info"] is not None else no()]
                for p,rec in zip(POLICIES,opts):
                    plans.append(dict(key=key,name=name,year=y2,new=new["version"],facet=f,policy=p,**rec))
    schedules={}
    for yr in YEARS[1:]:
        stage={r["key"]:r for r in trans if r["year"]==yr}
        b=len(stage)//3
        for p in POLICIES:
            grouped=Counter()
            for row in plans:
                if row["year"]==yr and row["policy"]==p and not row["present"]:grouped[row["key"]]+=1
            priority=sorted(stage,key=lambda k:(-grouped[k],sha((stage[k]["name"]+"|"+stage[k]["new"]).encode())))
            schedules[f"{yr}/{p}"]=priority[:b]
    put(ROOT/"source-fields.gz",sources_cache);put(ROOT/"transitions.json",trans);put(ROOT/"native.gz",native)
    put(ROOT/"predictions.gz",plans);put(ROOT/"reading-plans.json",schedules)
    names=["PROTOCOL_RU.md","artifacts.py","experiment.py","releases.json","native.gz","transitions.json","predictions.gz","reading-plans.json","source-fields.gz","upstream.json"]
    put(ROOT/"plan-lock.json",{n:sha((ROOT/n).read_bytes()) for n in names})
    print(len(trans),len(native),len(plans))

def stats(rows):
    n=len(rows);answers=sum(r["present"] for r in rows);correct=sum(r["correct"] for r in rows)
    return dict(n=n,correct=correct,wrong=answers-correct,abstained=n-answers,current_fields=sum(r["confirmed"] for r in rows),conditional=correct/answers if answers else None,
                fraction_correct=correct/n,coverage=answers/n,opens=sorted({r["key"] for r in rows if r["confirmed"]}),
                stale_wrong=sum(r["present"] and not r["correct"] and r["value"]==r["previous"] and r["truth"]!=r["previous"] for r in rows))
def interval(rows,pa,pb):
    by=defaultdict(dict)
    for r in rows:
        if r["policy"] in (pa,pb):by[r["name"],r["key"],r["facet"]][r["policy"]]=int(r["correct"])
    per=defaultdict(list)
    for (n,k,f),v in by.items():per[n].append(v[pa]-v[pb])
    blocks=[(sum(a),len(a)) for _,a in sorted(per.items())];rng=Random(4920);vals=[]
    for _ in range(10000):
        sample=rng.choices(blocks,k=len(blocks));vals.append(sum(x[0] for x in sample)/sum(x[1] for x in sample))
    vals.sort()
    return dict(delta=sum(x[0] for x in blocks)/sum(x[1] for x in blocks),ci95=[vals[249],vals[9749]],
                paired_gain=sum(v==1 for a in per.values() for v in a),paired_loss=sum(v==-1 for a in per.values() for v in a),
                by_project={k:[sum(v),len(v)] for k,v in per.items()})

def score():
    lock=get(ROOT/"plan-lock.json");assert all(sha((ROOT/k).read_bytes())==v for k,v in lock.items())
    data=get(ROOT/"releases.json");t={r["key"]:r for r in get(ROOT/"transitions.json")}
    truth={k:wheel(data[r["name"]]["snapshots"][str(r["year"])]["wheel"]) for k,r in t.items()}
    plans=get(ROOT/"predictions.gz");schedules=get(ROOT/"reading-plans.json");scores={};all_rows=[];contrasts={};cost={}
    for budget in ("none","third"):
        rows=[]
        for p in plans:
            k,f,pol=p["key"],p["facet"],p["policy"];old=t[k]["old_wheel"]["fields"][f];now=truth[k]["fields"][f]
            confirmed=budget=="third" and k in schedules[f"{p['year']}/{pol}"]
            answer=yes(now,"confirmed wheel") if confirmed else p
            rows.append({**p,**answer,"truth":now,"previous":old,"correct":bool(answer["present"] and answer["value"]==now),"confirmed":confirmed,"budget":budget})
        scores[budget]={pol:stats([r for r in rows if r["policy"]==pol]) for pol in POLICIES}
        contrasts[budget]={b:interval(rows,"typed",b) for b in ("same_file","current_static","previous")}
        cost[budget]={pol:{"wheel_archive_bytes":sum(t[k]["wheel_archive_bytes"] for k in s["opens"]),
                            "wheel_metadata_bytes":sum(truth[k]["member_bytes"] for k in s["opens"])} for pol,s in scores[budget].items()}
        all_rows.extend(rows)
    scores["all_wheels"]={"correct":sum(len(FACETS) for _ in truth),"opens":len(truth)}
    checks=dict(unique_projects=len({r["name"] for r in t.values()}),transitions=len(t),wave_n=dict(Counter(r["year"] for r in t.values())),
                n=len(t)*len(FACETS),changes={f:sum(z["old_wheel"]["fields"][f]!=truth[k]["fields"][f] for k,z in t.items()) for f in FACETS},
                current_pyproject_bytes=sum(r["py_bytes"] for r in t.values()),current_pkg_info_bytes=sum(r["pkg_info_bytes"] for r in t.values()),
                native_hits=sum(bool(x["items"]) for x in get(ROOT/"native.gz")))
    put(ROOT/"current-witness.gz",truth);put(ROOT/"outcomes.gz",all_rows)
    put(ROOT/"results.json",dict(scores=scores,typed_minus=contrasts,cost=cost,checks=checks))
    print(checks)
    for budget in ("none","third"):
        print(budget,[(m,s["correct"],s["wrong"],s["abstained"],len(s["opens"])) for m,s in scores[budget].items()],contrasts[budget]["same_file"])
if __name__=="__main__":
    if sys.argv[1]=="forecast":forecasts()
    elif sys.argv[1]=="score":score()

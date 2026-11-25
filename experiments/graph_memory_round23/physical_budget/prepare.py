"""Freeze a 192-trajectory numeric fixture from the two untouched native rankings."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import gzip,hashlib,json,sys
D=Path(__file__).resolve().parent;W=D.parents[1];R20=W/"graph_memory_round20"
R22=W/"graph_memory_round22/packing_control";BASE=R20/"residual_graph"
sys.path.insert(0,str(R20/"fine_train"))
import apply as app
from apply import rd,load,save,sha,np

def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def plan():
    cohort=load(W/"graph_memory_round18/isetrace_official/cohort.json")
    by={}
    for r in cohort:by.setdefault(r["trajectory_id"],[]).append(r["query_id"])
    tids=sorted(by,key=lambda t:digest("pack-update/trajectory/"+t))[:192]
    qs={t:min(by[t],key=lambda q:digest("pack-update/query/"+q)) for t in tids}
    parents=[D/"PROTOCOL_RU.md",R22/"MANIFEST_SHA256.json",BASE/"forecast-seal.json",BASE/"adjacency_control/full/forecast-seal.json",R20/"fine_train/model.json",R20/"fine_read/reader.py"]
    save(D/"plan.json",{"parents":{p.relative_to(W).as_posix():sha(p) for p in parents},"questions":qs,"budgets":[1024,1536,2048,3072],
                        "primary":"one-score-change/budget2048: exact-cached-repair minus whole indexed rebuild","source_code":sha(Path(__file__))})

def make(i):
    plan=load(D/"plan.json");qs=plan["questions"]
    root=BASE/"adjacency_control/full"
    def ranks(folder):
        name=f"forecasts-rgcn-{i}.json.gz";p=folder/name;assert load(folder/"forecast-seal.json")["forecasts"][name]==sha(p)
        return {r["q"]:r for r in load(p) if r["t"] in qs and qs[r["t"]]==r["q"]}
    main=ranks(root);other=ranks(BASE);assert main.keys()==other.keys()
    prev=R22/f"no-next-decisions-{i}.json.gz";assert sha(prev)==load(R22/"MANIFEST_SHA256.json")["files"][prev.name]
    ref={r["t"]:r["picks"][qs[r["t"]]]["ratio"] for r in load(prev) if r["t"] in qs};out=[]
    m=load(R20/"fine_train/model.json")["models"]["full"]
    with gzip.open(rd.blocks_path("rgcn",i),"rb") as handle:
        for line in handle:
            row=json.loads(line);t=row["t"]
            if t not in qs:continue
            q=qs[t];raw=load(rd.stream.CACHE/f"{i}-{t}.json.gz");text=dict(raw["q"])[q];bl=row["blocks"]
            rr=main[q]["rr"];alt=other[q]["rr"];geom=rd.geometry(row,raw,rr);cost=np.asarray([b[3] for b in bl])
            def priority(records):
                x,_,_=rd.features(text,records,bl,geom);z=x[:,m["columns"]]
                prob=1/(1+np.exp(-np.clip((z-m["mean"])/m["scale"]@m["coef"]+m["offset"],-200,200)))
                return prob/cost
            a,b=priority(rr),priority(alt)
            items=[[j,float(a[j]),float(b[j]),bl[j][3],*bl[j][:3]] for j in range(len(bl)) if geom[2][j]]
            assert all(np.isfinite(v[1:3]).all() and 0<v[3]<=504 for v in items)
            protect=[]
            for v in rr[:2]:
                nid=v["node_id"];e,l,h,c=geom[0][nid];protect.append([nid,c,e,l,h])
            assert sum(x[1] for x in protect)<=1024 and ref[t][:2]==[x[0] for x in protect]
            want=[int(k[6:]) for k in ref[t][2:]]
            out.append({"q":q,"t":t,"core":protect,"items":items,"strict2048":want})
    p=D/f"fixture-{i}.json.gz";save(p,out);return [p.name,sha(p),len(out),sum(len(a["items"]) for a in out)]

def build():
    with ProcessPoolExecutor(2) as ex:info=list(ex.map(make,range(8)))
    assert sum(x[2] for x in info)==192
    save(D/"fixtures.json",{"files":info,"plan":sha(D/"plan.json"),"code":sha(Path(__file__))})

if __name__=="__main__":{"plan":plan,"build":build}[sys.argv[1]]()


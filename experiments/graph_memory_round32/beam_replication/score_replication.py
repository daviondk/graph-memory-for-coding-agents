"""Post-seal paired comparisons, stage-specific physical cost and parity diagnostics."""
from collections import Counter
from math import comb
from statistics import mean,median
from itertools import combinations
import gzip,json
import numpy as np
from replicate import HERE,BEAM,read,put,sha,pool,BLIND,inputs
import sys
sys.path.insert(0,str(BEAM.parent/"support_pairs"))
from families import decision_family

def compare(v):
    order=v["order"];pairs=[tuple(r[:2]) for r in v["rows"]];rows=list(range(45))
    ids={p:i for i,p in enumerate(pairs)};ws=[ids[tuple(p)] for p in v["winners"]]
    assert ws==sorted(ws) and len(set(ws))==len(ws)
    static,_=decision_family(pairs,2);four=[i for i,p in enumerate(pairs) if set(p)&set(order[:4])]
    initial=[i for i,p in enumerate(pairs) if set(p)&set(order[:2])]
    star=sorted({i for r in order[:4] for i in [j for j in rows if r in pairs[j]][:3]})
    methods={"star_union":star,"lazy":ws,"pool4_matched":four[:len(ws)],"pool4":four,"global_matched":rows[:len(ws)],
             "initial":initial,"static":static,"full":rows}
    records={};scens=[]
    for k in (0,1,2):
        tall=Counter();diff=0
        for removed in combinations(range(10),k):
            eligible={ids[p] for p in pool(order,set(removed))}
            truth=min(eligible)
            got={m:next((idx for idx in vals if idx in eligible),None) for m,vals in methods.items()}
            static_initial=next((i for i in initial if not set(pairs[i])&set(removed)),None)
            got["initial_ungated"]=static_initial
            full_static=next(j for j,p in enumerate(pairs) if not set(p)&set(removed))
            diff+=int(truth!=full_static)
            tall.update({m:int(y==truth) for m,y in got.items()})
            assert truth==got["full"]==got["pool4"]==got["lazy"]==got["star_union"]
            scens.append([removed,truth,got])
        records[str(k)]={"n":comb(10,k),"exact":dict(tall),"ungated_changes":diff}
    c=Counter(x[0] for x in v["calls"])
    assert c["lazy"]==v["unique_lazy_pairs"]==30 and c["hop1"]==10 and c["pool4_remainder"]==0 and c["full_remainder"]==15
    return {"k":records,"memory_rows":{m:len(vals) for m,vals in methods.items()},"visited":len(v["trace"]),
            "phase_calls":dict(c),"phase_seconds":{phase:sum(x[3] for x in v["calls"] if x[0]==phase) for phase in c},
            "phase_tokens":{phase:sum(x[2] for x in v["calls"] if x[0]==phase) for phase in c},
            "unmemoized_pairs":v["uncached_tree_pair_calls"],"scenarios":scens}

def main():
    seal=read(HERE/"forecast-seal.json");plan=read(HERE/"plan.json")
    assert sha(HERE/"plan.json")==seal["plan"] and sha(HERE/"forecasts.json.gz")==seal["forecasts"] and seal["n"]==64
    assert read(HERE/"star-plan.json")["protocol"]==sha(HERE/"STAR_CONTROL_RU.md")
    raw=json.loads(gzip.decompress((HERE/"forecasts.json.gz").read_bytes()));assert set(raw)==set(plan["panel"])
    cases={q:compare(raw[q]) for q in plan["panel"]}
    b=json.dumps(cases,sort_keys=True,separators=(",",":")).encode()
    (HERE/"outcomes.json.gz").write_bytes(gzip.compress(b,mtime=0))
    put(HERE/"measure-seal.json",{"forecast":sha(HERE/"forecast-seal.json"),"outcomes":sha(HERE/"outcomes.json.gz"),
                                  "scorer":sha(HERE/"score_replication.py")})
    with gzip.open(BLIND.with_name("labels.json.gz"),"rt",encoding="utf8") as stream:labels=json.load(stream)
    src=inputs();methods=next(iter(cases.values()))["k"]["2"]["exact"]
    totals={k:{m:sum(row["k"][str(k)]["exact"][m] for row in cases.values()) for m in methods} for k in (0,1,2)}
    rng=np.random.default_rng(31463);paired={}
    index=rng.integers(64,size=(10000,64))
    for m in methods:
        delta=np.array([(r["k"]["2"]["exact"]["lazy"]-r["k"]["2"]["exact"][m])*100/45 for r in cases.values()])
        paired[m]={"delta_pp":float(delta.mean()),"ci_pp":np.quantile(delta[index].mean(1),[.025,.975]).tolist(),
                   "wins":int((delta>0).sum()),"ties":int((delta==0).sum()),"loss":int((delta<0).sum())}
    diff=np.array([r["memory_rows"]["star_union"]-r["memory_rows"]["lazy"] for r in cases.values()])
    saved={"mean_rows":float(diff.mean()),"ci_rows":np.quantile(diff[index].mean(1),[.025,.975]).tolist(),"wins":int((diff>0).sum()),"ties":int((diff==0).sum())}
    hits=0
    for q,row in cases.items():
        best=row["scenarios"][0][1];ids=raw[q]["rows"][best][:2]
        hits+=int({src[q]["titles"][i] for i in ids}==set(labels[q]["support"]))
    report={"n":len(cases),"k_correct":totals,"star_minus_lazy_saved":saved,"gold_initial_hits":hits,"paired":paired,
        "mean_memory_rows":{m:mean(r["memory_rows"][m] for r in cases.values()) for m in next(iter(cases.values()))["memory_rows"]},
        "lazy_pairs":sorted({r["phase_calls"]["lazy"] for r in cases.values()}),"raw_pairs":45,"pool4":30,
        "mean_without_memo":mean(r["unmemoized_pairs"] for r in cases.values()),
        "median_phase_s":{p:median(r["phase_seconds"][p] for r in cases.values()) for p in ("hop1","lazy","full_remainder")},
        "mean_phase_tokens":{p:mean(r["phase_tokens"][p] for r in cases.values()) for p in ("hop1","lazy","full_remainder")},
        "order_changed":sum(r["k"]["2"]["ungated_changes"] for r in cases.values()),"seed_bootstrap":31463,
        "outcomes":sha(HERE/"outcomes.json.gz"),"measure_seal":sha(HERE/"measure-seal.json")}
    put(HERE/"results.json",report)
    print(json.dumps(report["paired"]["pool4_matched"]))
if __name__=="__main__":main()

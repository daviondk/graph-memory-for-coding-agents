"""Check immutable outcome and graph identities and record independent aggregate counts."""
from pathlib import Path
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import statistics

D=Path(__file__).resolve().parent
def data(name):
    p=D/name;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def filehash(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def status(reports):
    failures={q[0] for q in reports if q[1]=="failed"}
    if "setup" in failures or "teardown" in failures:return "error"
    return next((out for phase,out,_ in reports if phase=="call"),"unresolved")
def main():
    roster=data("roster.json");w=D.parents[1];agent=w/"graph_memory_round7/reader"
    assert roster["ids"]==sorted(data("collection-inputs.json")["ids"])
    for name,h in roster["replica"].items():assert filehash(D/name)==h
    assert filehash(agent/"assign.json")==roster["r7_sha"]
    assert filehash(w/"graph_memory_round8/agent/assign.json")==roster["r8_sha"]
    for iid,entries in data("collection-inputs.json")["sources"].items():
        for name,h in entries.items():assert filehash(agent/"tasks"/iid/name)==h
    for name,h in data("prediction-lock.json").items():assert filehash(D/name)==h
    graphs={(r["task"],r["direction"]):r for r in data("graphs.json.gz")}
    forecasts={(r["task"],r["direction"],r["node"]):r for r in data("forecasts.json.gz")}
    final={(r["task"],r["direction"],r["node"]):r for r in data("outcomes.json")}
    decisions=data("verification.json")
    assert len(graphs)==2*len(roster["ids"]) and len(forecasts)==len(decisions)
    assert len(final)==sum(v["eligible"] for v in decisions)
    bins=defaultdict(Counter)
    issue=defaultdict(lambda:defaultdict(Counter));vers=set();observed_walls=[]
    for task in roster["ids"]:
        tests=set(data(f"runs/{task}/nodes.json"))
        for way,old,new in [("fix","base","gold"),("revert","gold","base")]:
            fragment=graphs[task,way];changed=set(fragment["changed"]);shared=set(fragment["edges"].get("shared",[]))
            prev=data(f"runs/{task}/{old}.json.gz");curr=data(f"runs/{task}/{new}.json.gz")
            vers.add((prev['python'],prev['pytest'],prev['coverage']))
            observed_walls.append(prev["wall"])
            initial=data(f"runs/{task}/testmon-{old}_build.json")
            rerun=data(f"runs/{task}/testmon-{new}_select.json")
            assert set(initial["reports"])==tests
            for test in tests:
                token=(task,way,test);r=forecasts[token]
                exact=bool(changed & (shared|set(fragment["edges"].get(test,[]))))
                assert r["selected"]["symbol"]==exact
                assert all(not exact or r["selected"][arm] for arm in ("bloom512","bloom2048","shared512","shared2048"))
                if token not in final:continue
                v=final[token]
                assert status(prev['reports'][test])==v['prior'] and status(curr['reports'][test])==v['actual']
                assert (test in rerun['reports'])==v['selected']['testmon']
                assert v["changed"]==(v['prior']!=v['actual'])
                for arm,sel in v["selected"].items():
                    key=f"{way}/{arm}";b=bins[key];b['n']+=1;b['rerun']+=sel;b['stale']+=v['changed'] and not sel
                    b['missed_fail']+=v['new_failure'] and not sel
                    ctr=issue[task][key];ctr['rerun']+=sel;ctr['stale']+=v['changed'] and not sel
    result=data("results.json")
    for key,a in bins.items():
        way,arm=key.split("/")
        x=result[way]["policies"][arm]
        assert (a["n"],a["rerun"],a["stale"],a["missed_fail"])==(result[way]["n"],x['rerun'],x['stale'],x["missed_new_failures"])
    saved=[s for s in ("roster.json","collection-inputs.json","collection-errors.json","graphs.json.gz","forecasts.json.gz",
        "testmon-input.json","testmon-errors.json","verification.json","outcomes.json","results.json","storage.json","db-costs.json") if (D/s).exists()]
    doc=dict(tasks=roster["ids"],python_pytest_coverage=sorted(vers),testmon=data("testmon-input.json")["version"],
             graphs=len(graphs),forecasts=len(forecasts),eligible=len(final),median_full_pytest_wall=statistics.median(observed_walls),
             counters=dict(bins),by_issue={k:dict(v) for k,v in issue.items()},hashes={s:filehash(D/s) for s in saved})
    (D/"audit.json").write_text(json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(len(graphs),len(forecasts),len(final),sorted(vers))
if __name__=="__main__":main()

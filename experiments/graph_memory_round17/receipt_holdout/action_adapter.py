"""Respect skip statuses in the positive-receipt cohort; compare real executions, with exact block bootstrap weights."""
import collections
import itertools
import json
import math
import tempfile
import time
from pathlib import Path
from run_holdout import PRIMARY,ROOT
import observe,rollback,testmon_comparison
from testmon_comparison import as_node,call,outcome

def exact_ci(rows):
    n=len(rows);den=n**n
    weight=collections.Counter()
    # The multinomial multiset sum is identical to enumerating all n**n ordered draws.
    for picks in itertools.combinations_with_replacement(range(n),n):
        counts=collections.Counter(picks)
        multiplicity=math.factorial(n)//math.prod(math.factorial(v) for v in counts.values())
        value=sum(rows[i]["benefit"] for i in picks)/sum(rows[i]["n"] for i in picks)
        weight[value]+=multiplicity
    assert sum(weight.values())==den
    def quantile(q):
        i=int(q*(den-1));acc=0
        for v,mass in sorted(weight.items()):
            acc+=mass
            if i<acc:return v
        raise AssertionError(i)
    return [quantile(.025),quantile(.975)]
def main():
    for m in (observe,rollback,testmon_comparison):m.ROOT=ROOT
    cache=Path("D:/CodexResearch/x20-round17-test-holdout");cache.mkdir(exist_ok=True)
    roster=rollback.read(ROOT/"rollback-roster.json")["blocks"];official=rollback.read(ROOT/"testmon-graded.gz")
    put=observe.put
    put("action-adapter-lock.json",{"code":observe.sha((ROOT/"action_adapter.py").read_bytes()),"original_graph_forecasts":observe.sha((ROOT/"testmon-graph-forecasts.gz").read_bytes()),"eligibility":"retain every native baseline nodeid in the logs, issue reusable receipts only for confirmed baseline success; nonpass always requires recheck"})
    paired=[];evidence={}
    with tempfile.TemporaryDirectory(dir=cache/"testmon") as tmp:
        for b in roster:
            c=b["commit"];cwd=Path(tmp)/c/"work";sink=cwd.parent/"logs";sink.mkdir(parents=True);rollback.build(b,cwd)
            nodes=[as_node(v["name"]) for v in b["tests"]]
            initial=call(cwd,sink,"capture",nodes,False,True)
            current=initial["native"]["rows"];fold=[r for r in official if r["commit"]==c]
            positive={v["node"] for v in fold}
            assert {node for node in nodes if outcome(current[node])=="pass"}==positive
            before=(cwd/b["module"]).read_bytes();after=rollback.source(b["parent"],b["module"])
            (cwd/b["module"]).write_bytes(after)
            assert observe.sha(after)==b["before_sha"]
            start=time.perf_counter();old,oa=rollback.structure(before);new,na=rollback.structure(after);assert old.keys()==new.keys() and oa==na
            changed={n for n in old if old[n]!=new[n]};assert changed==set(b["changed"])
            edges={n:sorted(fn for f,fn in current[n]["calls"] if f==b["module"]) for n in positive}
            chosen=[n for n in nodes if n in positive and changed.intersection(edges[n])]
            no_receipt=sorted(set(nodes)-positive)
            assert set(chosen)=={v["node"] for v in fold if v["graph_recheck"]}
            seconds=time.perf_counter()-start
            targets=chosen+no_receipt;final=call(cwd,sink,"execute",targets,False,False) if targets else None
            found={node:outcome(r) for node,r in final["native"]["rows"].items()} if final else {}
            assert found.keys()==set(targets) and all(found[v["node"]]==v["truth"] for v in fold if v["graph_recheck"])
            evidence[c]={"initial":initial,"final":final,"classify_seconds":seconds,"edges_bytes_for_changed_file":len(json.dumps(edges,separators=(",",":")).encode()),"edges":edges,"choose":targets,"valid_receipt_choose":chosen,"no_receipt":no_receipt,"outcomes":found}
            tm=sum(v["testmon_recheck"] for v in fold)
            paired.append({"id":c,"n":len(fold),"testmon":tm,"graph":len(chosen),"benefit":tm-len(chosen),"fails":sum(v["truth"]=="fail" for v in fold)})
    put("graph-actions.gz",evidence)
    pos=sum(v["benefit"]>0 for v in paired);neg=sum(v["benefit"]<0 for v in paired)
    sign=min(1.,2*sum(math.comb(pos+neg,i) for i in range(min(pos,neg)+1))/2**(pos+neg))
    res={"pairs":paired,"initial_seconds":sum(v["initial"]["seconds"] for v in evidence.values()),"graph_ast_selection_seconds":sum(v["classify_seconds"] for v in evidence.values()),"test_invocation_seconds":sum(v["final"]["seconds"] for v in evidence.values() if v["final"]),"selected_ran":sum(len(v["outcomes"]) for v in evidence.values()),"total_capture_edges_bytes_changed_file":sum(v["edges_bytes_for_changed_file"] for v in evidence.values()),"commit_cluster_percentile_95":exact_ci(paired),"commit_exact_sign_p":sign,"additional_without_pass":sum(len(v["no_receipt"]) for v in evidence.values())}
    put("graph-actions-results.json",res);print(res)
if __name__=="__main__":main()

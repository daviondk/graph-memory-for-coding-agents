"""Recreate the sparse receipt graph, actually dispatch its selected pytest nodes, and compare to native selection."""
import itertools
import json
import os
import tempfile
import time
from testmon_comparison import ROOT, CACHE, as_node, build, call, outcome, put, read, sha, source
from rollback import structure

def main():
    original=read(ROOT/"testmon-graded.gz")
    roster=read(ROOT/"rollback-roster.json")["blocks"]
    assigned={n:sha((ROOT/n).read_bytes()) for n in ("GRAPH_ACTION_PROTOCOL_RU.md","execute_graph.py","rollback-roster.json","testmon-forecast-seal.json")}
    put("graph-action-lock.json",assigned)
    evidence={};paired=[]
    with tempfile.TemporaryDirectory(dir=CACHE/"testmon") as tmp:
        for block in roster:
            c=block["commit"];base=os.path.join(tmp,c,"work")
            from pathlib import Path
            base=Path(base);sink=base.parent/"audit";sink.mkdir(parents=True)
            build(block,base)
            nodes=[as_node(r["name"]) for r in block["tests"]]
            initial=call(base,sink,"capture",nodes,False,True)
            assert set(initial["native"]["rows"])==set(nodes) and all(outcome(r)=="pass" for r in initial["native"]["rows"].values())
            before=(base/block["module"]).read_bytes()
            after=source(block["parent"],block["module"])
            (base/block["module"]).write_bytes(after)
            assert sha(after)==block["before_sha"]
            t=time.perf_counter()
            old,old_global=structure(before);new,new_global=structure(after)
            assert old.keys()==new.keys() and old_global==new_global
            changed={n for n in old if old[n]!=new[n]};assert changed==set(block["changed"])
            edges={n:sorted(z[1] for z in r["calls"] if z[0]==block["module"]) for n,r in initial["native"]["rows"].items()}
            choose=[n for n in nodes if set(edges[n])&changed]
            took=time.perf_counter()-t
            expected={r["node"] for r in original if r["commit"]==c and r["graph_recheck"]};assert set(choose)==expected
            final=call(base,sink,"selected",choose,False,False) if choose else None
            found={n:outcome(r) for n,r in final["native"]["rows"].items()} if final else {}
            assert set(found)==set(choose)
            assert all(found[r["node"]]==r["truth"] for r in original if r["commit"]==c and r["graph_recheck"])
            evidence[c]={"initial":initial,"final":final,"classify_seconds":took,"edges_bytes_for_changed_file":len(json.dumps(edges,separators=(",",":")).encode()),"edges":edges,"choose":choose,"outcomes":found}
            block_rs=[r for r in original if r["commit"]==c]
            testmon=sum(r["testmon_recheck"] for r in block_rs)
            paired.append({"id":c,"n":len(block_rs),"testmon":testmon,"graph":len(choose),"benefit":testmon-len(choose),"fails":sum(r["truth"]=="fail" for r in block_rs)})
    put("graph-actions.gz",evidence)
    n=len(paired);deltas=sorted(sum(r["benefit"] for r in sample)/sum(r["n"] for r in sample) for sample in itertools.product(paired,repeat=n))
    n_pos=sum(r["benefit"]>0 for r in paired);n_neg=sum(r["benefit"]<0 for r in paired)
    from math import comb
    sign_p=min(1.,2*sum(comb(n_pos+n_neg,i) for i in range(min(n_pos,n_neg)+1))/(2**(n_pos+n_neg)))
    results={"pairs":paired,"initial_seconds":sum(v["initial"]["seconds"] for v in evidence.values()),"graph_ast_selection_seconds":sum(v["classify_seconds"] for v in evidence.values()),"test_invocation_seconds":sum(v["final"]["seconds"] for v in evidence.values() if v["final"]),"selected_ran":sum(len(v["outcomes"]) for v in evidence.values()),"total_capture_edges_bytes_changed_file":sum(v["edges_bytes_for_changed_file"] for v in evidence.values()),"commit_cluster_percentile_95":[deltas[int(.025*(len(deltas)-1))],deltas[int(.975*(len(deltas)-1))]],"commit_exact_sign_p":sign_p}
    put("graph-actions-results.json",results);print(results)
if __name__=="__main__":main()

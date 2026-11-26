"""Replay a frozen, outcome-blind panel with native OR-Tools integer knapsack solvers."""
from pathlib import Path
import ctypes
import gzip
import hashlib
import importlib.metadata
import json
import random
import statistics
import sys
from time import perf_counter_ns
from ortools.algorithms.python import knapsack_solver as ks

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench_core import Case, build, read

def digest(data):
    return hashlib.sha256(data).hexdigest()

def panel_key(q):
    return digest(("classic-r49:" + q).encode())

def prepare(data):
    result = []
    costs = data["cost"]
    for _, _, ids, profits, _ in data["states"]:
        used, split = 0, 0
        while split < len(ids) and used + costs[ids[split]] <= 1024:
            used += costs[ids[split]]
            split += 1
        head = ids[:split]
        room = 2048 - used
        tail = [(i, costs[i], v) for i,v in zip(ids[split:], profits[split:]) if costs[i] <= room and v > 0]
        result.append((head, room, tail))
    return result

def google(mode, data):
    kind = (ks.SolverType.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER if mode=="google_bnb"
            else ks.SolverType.KNAPSACK_DYNAMIC_PROGRAMMING_SOLVER)
    packets = []
    for head,room,tail in prepare(data):
        if sum(c for _,c,_ in tail) <= room:
            packets.append(head + [i for i,_,_ in tail])
            continue
        # Fold zero-weight profitable items out identically, retaining original rank in output.
        regular = [(i,c,v) for i,c,v in tail if c>0]
        solver = ks.KnapsackSolver(kind,"r49")
        solver.init([v for _,_,v in regular], [[c for _,c,_ in regular]], [room])
        optimum = solver.solve()
        assert solver.is_solution_optimal()
        chosen = {i for j,(i,_,_) in enumerate(regular) if solver.best_solution_contains(j)}
        assert sum(v for i,_,v in regular if i in chosen)==optimum
        packets.append(head + [i for i,c,_ in tail if c==0 or i in chosen])
    return packets

def main():
    assert digest((HERE/"PROTOCOL_RU.md").read_bytes())=="0dcfe62e61faadc838d6e09bacf12d03b16270b1ac2936efc61ca60bca5fc1df"
    src=HERE.parents[1]/"learned_stream"/"input-13.json.gz"
    assert digest(src.read_bytes())=="3886b8ab29eb61728cc2d235d3fc7a1bc89cb645c9b06ddb2dd485a1c5bf6f36"
    assert importlib.metadata.version("ortools")=="9.15.6755"
    raw=read(src)
    panel=sorted(raw,key=panel_key)[:128]
    cases={q:Case(raw[q]) for q in panel}
    fn=build()
    names=["canonical_dp","canonical_core","google_bnb","google_dp"]
    timings=[]
    once={}
    rng=random.Random(49088)
    for rep in range(4):
        qs=panel.copy();rng.shuffle(qs)
        for q in qs:
            modes=names.copy();rng.shuffle(modes)
            for mode in modes:
                start=perf_counter_ns()
                if mode.startswith("google"):
                    packets=google(mode,raw[q])
                else:
                    case=cases[q];case.run(fn,0 if mode=="canonical_dp" else 2);packets=case.copy()
                dt=perf_counter_ns()-start
                if rep:timings.append([q,rep,mode,dt])
                key=(q,mode)
                if key in once:assert packets==once[key]
                else:once[key]=packets
    rows=[]
    for q in panel:
        cost=raw[q]["cost"]
        for j,(_,_,ids,values,_) in enumerate(raw[q]["states"]):
            by_id=dict(zip(ids,values))
            outputs={name:once[q,name][j] for name in names}
            totals={name:sum(by_id[i] for i in packet) for name,packet in outputs.items()}
            assert len(set(totals.values()))==1
            assert outputs[names[0]]==outputs[names[1]]
            for packet in outputs.values():
                assert sum(cost[i] for i in packet)<=2048
                assert packet==[i for i in ids if i in set(packet)]
            rows.append({"query":q,"trajectory":raw[q]["t"],"step":j,"objective":totals[names[0]],"packets":outputs})
    repeat={name:[sum(t for q,r,m,t in timings if m==name and r==rep)/1e6 for rep in [1,2,3]] for name in names}
    summary={"queries":128,"trajectories":len({x["trajectory"] for x in rows}),"snapshots":len(rows),
              "objective_matches":{m:len(rows) for m in names},"ordered_matches":{m:sum(x["packets"][m]==x["packets"][names[0]] for x in rows) for m in names},
              "max_objective":max(x["objective"] for x in rows),"objectives_over_int32":sum(x["objective"]>2**31-1 for x in rows),
              "timed_total_ms_by_rep":repeat,"median_total_ms":{m:statistics.median(t) for m,t in repeat.items()},
              "platform":sys.platform,"python":sys.version,"ortools":"9.15.6755","ortools_extension_sha256":digest(Path(ks.__file__).read_bytes())}
    for filename,data in [("ledger.json.gz",rows),("timings.json.gz",timings),("results.json",summary)]:
        payload=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
        (HERE/filename).write_bytes(gzip.compress(payload,mtime=0) if filename.endswith("gz") else payload)
    print(json.dumps(summary))
if __name__=="__main__":
    main()

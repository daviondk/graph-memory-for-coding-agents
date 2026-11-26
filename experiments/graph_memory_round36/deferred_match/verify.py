"""Independent checks using the standard library and previously signed trajectory files."""
from pathlib import Path
from collections import Counter
from hashlib import sha256
import gzip,json,math,random

D=Path(__file__).resolve().parent
def read(path):
    return json.loads(gzip.decompress(path.read_bytes()) if path.suffix==".gz" else path.read_bytes())
def digest(path):
    return sha256(path.read_bytes()).hexdigest()
def main():
    s=read(D/"summary.json"); reg=read(D/"plan.json"); cs=read(D/"counter-seal.json")
    ts=read(D/"timing-seal.json")
    assert cs["plan"]==ts["plan"]==digest(D/"plan.json")
    assert reg["operator"]==digest(D/"operator_match.py") and reg["protocol"]==digest(D/"PROTOCOL_RU.md")
    assert reg["baseline_manifest"]==digest(D.parent/"streaming_witnesses"/"manifest.json")
    assert digest(D/"timing.py")==ts["code"] and digest(D/"measure.py")==cs["code"]
    corpus={};tall=Counter();cut=Counter()
    for i in range(8):
        f=D/f"counters-{i}.json.gz";assert cs["files"][f.name]==digest(f)
        geom=read(D.parent/"materialized_append"/f"graphs-{i}.json.gz")
        baseline=read(D.parent/"streaming_witnesses"/f"histories-{i}.json.gz")
        for t,obs in read(f).items():
            assert t not in corpus
            counts=obs["counts"];corpus[t]=counts;tall.update(counts)
            assert counts["calls"]==counts["outputs"]
            assert counts["event_checks"]==baseline[t]["steps"]==2*counts["calls"]
            assert counts["observed_identity_integral"]==baseline[t]["checked_live_pairs"]
            assert set(obs["cuts"])=={"25","50","75","100"}
            for name,(logical,pu) in obs["cuts"].items():
                target=geom[t]["states"][name]
                assert logical==target["logical_pairs"]["M"] and pu==target["material"]
                cut[name]+=1
    assert s["totals"]==dict(tall) and sum(cut.values())==s["all_cut_checks"]==4828
    assert tall["predicate_old"]-tall["predicate_new"]==sum(tall[k] for k in ("collision_saved","zero_target_saved","invisible_source_saved"))
    assert ts["samples"]==digest(D/"timings.json.gz")
    panel=sorted(corpus,key=lambda t:sha256(("R36-deferred-match-cpu|"+t).encode()).digest())[:96]
    timings=read(D/"timings.json.gz");assert list(reg["timed_ids"])==panel and set(panel)==set(timings)
    assert all(len(v["measurements"])==4 for v in timings.values())
    for i,c in enumerate(("process_ns","wall_ns","thread_cycles")):
        for arm,vals in s["timing"].items():
            actual=sum(rep[arm][i] for v in timings.values() for rep in v["measurements"])/4
            assert actual==vals[c]["summed"]
            if arm!="eager":
                ratio=actual/s["timing"]["eager"][c]["summed"]
                assert math.isclose(ratio,vals[c]["vs_eager"]["ratio"])
    for t,v in timings.items():
        assert tuple(v["actual_sql_receipts"])==tuple(corpus[t].get(k,0) for k in ("lookups","lookup_raw_bytes","lookup_structured_bytes"))
    tests=read(D/"fixture_results.json")
    assert len(tests)==10 and all(v["equality"]!=k.startswith("counterexample_") for k,v in tests.items())
    print("Checked",len(corpus),"trajectories,",sum(cut.values()),"cuts,",len(timings),"timed trajectory blocks and",len(tests),"fixture outcomes.")
if __name__=="__main__":main()

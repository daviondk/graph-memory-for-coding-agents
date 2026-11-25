"""Verify portable construction and timings; optionally replay native library and inputs."""
import argparse
from pathlib import Path
from bench import D,read,save,sha
FILES=("PROTOCOL_RU.md","frontiers.py","bench.py","plan.json","analyze.py","results.json","NATIVE_RU.md",
       "build_endpoint.cpp","native.py","native-plan.json","native-results.json","alternative.py","alternative.json","REPORT_RU.md","verify.py")
def main():
    p=argparse.ArgumentParser();p.add_argument("--seal",action="store_true");p.add_argument("--private",action="store_true");args=p.parse_args()
    r=read(D/"results.json");n=read(D/"native-results.json");v=read(D/"alternative.json")
    assert r["complete_parity_comparisons"]==1152 and r["stress_parity"]==64 and r["records"]==3059
    assert n["parity"]==864 and read(D/"plan.json")["test_comparisons"]==280 and n["precision_checks"]==420
    assert n["plan"]==sha(D/"native-plan.json") and r["plan"]==sha(D/"plan.json") and v["native"]==sha(D/"native-results.json")
    data_paths={**{k:h for k,h in r["runs"].items() if not k.startswith("native-")},**n["runs"]}
    assert len(data_paths)==29
    for path,h in data_paths.items():assert sha(D/"runs"/path)==h
    if args.private:
        from native import LIB,precision
        from bench import tests
        assert sha(LIB)==read(D/"native-plan.json")["library"] and tests()==280 and precision()==420
    hashes={f:sha(D/f) for f in FILES}
    hashes.update({"runs/"+p:h for p,h in data_paths.items()})
    dest=D/"manifest.json"
    if args.seal and not dest.exists():save(dest,hashes)
    assert read(dest)==hashes;print("verified",len(hashes),sha(dest))
if __name__=="__main__":main()
